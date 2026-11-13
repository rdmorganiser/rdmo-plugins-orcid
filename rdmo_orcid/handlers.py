from django.conf import settings
from django.dispatch import receiver

import dpath
import requests

from rdmo.core.utils import import_class
from rdmo.domain.models import Attribute
from rdmo.projects.models import Value
from rdmo.projects.signals import value_created, value_updated

from .utils import find_parent, find_question, find_set, get_child_prefix


@receiver(value_created, sender=Value)
@receiver(value_updated, sender=Value)
def orcid_handler(signal, sender, instance=None, **kwargs):
    handler_class = import_class(getattr(settings, 'ORCID_HANDLER', 'rdmo_orcid.handlers.OrcidHandler'))
    handler_class().handle(instance)


class OrcidHandler:
    def handle(self, instance):
        # check for ORCID_PROVIDER_MAP
        if not getattr(settings, 'ORCID_PROVIDER_MAP', None):
            return

        # check if this value instance has an external_id or has an attribute (it may have been deleted)
        if not instance.external_id or not instance.attribute_id:
            return

        # loop over ORCID_PROVIDER_MAP and check if the value instance attribute is found
        for attribute_map in settings.ORCID_PROVIDER_MAP:
            if 'orcid' in attribute_map and instance.attribute.uri == attribute_map['orcid']:
                # query the orcid api for the record for this orcid
                data = self.fetch_orcid_data(instance.external_id)
                if data is None:
                    return

                self.instance = instance

                # prefetch catalog
                self.catalog = instance.project.catalog
                self.catalog.prefetch_elements()

                # compute answer_tree
                self.answer_tree = instance.project.get_answer_tree(verbose='question')

                if 'given_name' in attribute_map:
                    self.save_value(attribute_map['given_name'], self.get_given_name(data))

                if 'family_name' in attribute_map:
                    self.save_value(attribute_map['family_name'], self.get_family_name(data))

                if 'affiliation_name' in attribute_map:
                    self.save_values(attribute_map['affiliation_name'], self.get_affiliation_names(data))

                if 'affiliation_ror' in attribute_map:
                    self.save_values(attribute_map['affiliation_ror'], self.get_affiliation_rors(data))

    def save_value(self, attribute_uri, text):
        attribute = Attribute.objects.get(uri=attribute_uri)
        if question := find_question(self.catalog, attribute):
            if value_set := find_set(self.answer_tree, question, self.instance):
                Value.objects.update_or_create(
                    project=self.instance.project,
                    snapshot=None,
                    attribute=attribute,
                    set_prefix=value_set.get('set_prefix'),
                    set_index=value_set.get('set_index'),
                    defaults={
                        'text': text,
                    },
                )

    def save_values(self, attribute_uri, texts):
        attribute = Attribute.objects.get(uri=attribute_uri)
        question = find_question(self.catalog, attribute)
        if question is None:
            return

        parent = find_parent(self.catalog, question)

        # if the question of the instance is inside the parent, the sets of the parent belong to different entities
        instance_question = find_question(self.catalog, self.instance.attribute)
        create_parent_sets = parent and parent.is_collection and instance_question not in parent.descendants

        if question.is_collection:
            # the question is a collection: every text gets its own collection_index
            if value_set := find_set(self.answer_tree, question, self.instance):
                for collection_index, text in enumerate(texts):
                    if text:
                        Value.objects.update_or_create(
                            project=self.instance.project,
                            snapshot=None,
                            attribute=attribute,
                            set_prefix=value_set.get('set_prefix'),
                            set_index=value_set.get('set_index'),
                            collection_index=collection_index,
                            defaults={
                                'text': text,
                            },
                        )

                # delete the values for this attribute with surplus collection_indexes or without a text
                Value.objects.filter(
                    project=self.instance.project,
                    snapshot=None,
                    set_prefix=value_set.get('set_prefix'),
                    set_index=value_set.get('set_index'),
                    attribute=attribute,
                ).exclude(
                    collection_index__in=[collection_index for collection_index, text in enumerate(texts) if text],
                ).delete()

        elif create_parent_sets:
            # the parent is a collection: every text gets its own set of the parent,
            # we look for the set containing the parent, since the parent might not have any sets yet
            if value_set := find_set(self.answer_tree, parent, self.instance):
                set_prefix = get_child_prefix(value_set)

                for set_index, text in enumerate(texts):
                    if text:
                        Value.objects.update_or_create(
                            project=self.instance.project,
                            snapshot=None,
                            attribute=attribute,
                            set_prefix=set_prefix,
                            set_index=set_index,
                            defaults={
                                'text': text,
                            },
                        )

                # delete the values for this attribute in surplus sets or in sets without a text
                Value.objects.filter(
                    project=self.instance.project,
                    snapshot=None,
                    set_prefix=set_prefix,
                    attribute=attribute,
                ).exclude(
                    set_index__in=[set_index for set_index, text in enumerate(texts) if text],
                ).delete()

        else:
            # neither is a collection: only the first text is stored
            if texts and texts[0]:
                self.save_value(attribute_uri, texts[0])

    def fetch_orcid_data(self, orcid):
        url = getattr(settings, 'ORCID_PROVIDER_URL', 'https://pub.orcid.org/v3.0/').rstrip('/')
        headers = getattr(settings, 'ORCID_PROVIDER_HEADERS', {})

        try:
            response = requests.get(
                f'{url}/{orcid}',
                headers={**headers, 'Accept': 'application/json'},
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None

    def get_given_name(self, data):
        return dpath.get(data, '/person/name/given-names/value', default='')

    def get_family_name(self, data):
        return dpath.get(data, '/person/name/family-name/value', default='')

    def get_affiliation_names(self, data):
        affiliations = []
        for affiliation in dpath.get(data, '/activities-summary/employments/affiliation-group', default=[]):
            for summary in affiliation.get('summaries'):
                if dpath.get(summary, '/employment-summary/end-date', default=None) is None:
                    affiliations.append(self.get_affiliation_name(summary))
        return affiliations

    def get_affiliation_name(self, summary):
        return dpath.get(summary, '/employment-summary/organization/name', default=None)

    def get_affiliation_rors(self, data):
        affiliations = []
        for affiliation in dpath.get(data, '/activities-summary/employments/affiliation-group', default=[]):
            for summary in affiliation.get('summaries'):
                if dpath.get(summary, '/employment-summary/end-date', default=None) is None:
                    affiliations.append(self.get_affiliation_ror(summary))
        return affiliations

    def get_affiliation_ror(self, summary):
        try:
            disambiguation_source = dpath.get(
                summary,
                '/employment-summary/organization/disambiguated-organization/disambiguation-source',
            )
            disambiguation_id = dpath.get(
                summary,
                '/employment-summary/organization/disambiguated-organization/disambiguated-organization-identifier',
            )
        except KeyError:
            return None

        if disambiguation_source == 'ROR':
            return self.normalize_ror(disambiguation_id)
        elif disambiguation_source == 'RINGGOLD':
            return self.fetch_ror_from_wikidata(disambiguation_id)
        elif disambiguation_source in ['GRID', 'FUNDREF']:
            return self.fetch_ror(disambiguation_id)
        else:
            return None

    def fetch_ror_from_wikidata(self, ringgold_id):
        url = getattr(settings, 'WIKIDATA_PROVIDER_URL', 'https://www.wikidata.org/w/api.php')
        headers = getattr(settings, 'ORCID_PROVIDER_HEADERS', {})

        # wikidata requires a user agent, see https://meta.wikimedia.org/wiki/User-Agent_policy
        if not headers.get('User-Agent'):
            return None

        try:
            entity_response = requests.get(
                url,
                params={
                    'action': 'query',
                    'list': 'search',
                    'srsearch': f'haswbstatement:P3500={ringgold_id}',
                    'format': 'json',
                },
                headers=headers,
            )
            entity_response.raise_for_status()
            entity_response_data = entity_response.json()
        except requests.exceptions.RequestException:
            return None

        try:
            entity = dpath.get(entity_response_data, '/query/search/0/title')
        except KeyError:
            return None

        try:
            ror_response = requests.get(
                url,
                params={
                    'action': 'wbgetclaims',
                    'entity': entity,
                    'property': 'P6782',
                    'format': 'json',
                },
                headers=headers,
            )
            ror_response.raise_for_status()
            ror_response_data = ror_response.json()
        except requests.exceptions.RequestException:
            return None

        try:
            return self.normalize_ror(dpath.get(ror_response_data, '/claims/P6782/0/mainsnak/datavalue/value'))
        except KeyError:
            return None

    def fetch_ror(self, disambiguation_id):
        url = getattr(settings, 'ROR_PROVIDER_URL', 'https://api.ror.org/v2/').rstrip('/')
        headers = getattr(settings, 'ORCID_PROVIDER_HEADERS', {})

        try:
            response = requests.get(
                f'{url}/organizations',
                params={'query': disambiguation_id},
                headers=headers,
            )
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.RequestException:
            return None

        try:
            return self.normalize_ror(dpath.get(response_data, '/items/0/id'))
        except KeyError:
            return None

    def normalize_ror(self, ror):
        return ror.replace('https://ror.org/', '')
