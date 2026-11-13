from django.conf import settings
from django.dispatch import receiver

import dpath
import requests

from rdmo.domain.models import Attribute
from rdmo.projects.models import Value
from rdmo.projects.signals import value_created, value_updated

from .utils import find_parent, find_question, find_set, get_child_prefix


@receiver(value_created, sender=Value)
@receiver(value_updated, sender=Value)
def orcid_handler(signal, sender, instance=None, **kwargs):
    # check for ORCID_PROVIDER_MAP
    if not getattr(settings, 'ORCID_PROVIDER_MAP', None):
        return

    # check if we are importing fixtures
    if kwargs.get('raw'):
        return

    # check if this value instance has an external_id or has an attribute (it may have been deleted)
    if not instance.external_id or not instance.attribute_id:
        return

    # prefetch catalog
    catalog = instance.project.catalog
    catalog.prefetch_elements()

    # compute answer_tree
    answer_tree = instance.project.get_answer_tree(verbose='question')

    # loop over ORCID_PROVIDER_MAP and check if the value instance attribute is found
    for attribute_map in settings.ORCID_PROVIDER_MAP:
        if 'orcid' in attribute_map and instance.attribute.uri == attribute_map['orcid']:
            # query the orcid api for the record for this orcid
            try:
                url = getattr(settings, 'ORCID_PROVIDER_URL', 'https://pub.orcid.org/v3.0/').rstrip('/')
                headers = getattr(settings, 'ORCID_PROVIDER_HEADERS', {})
                headers['Accept'] = 'application/json'

                response = requests.get(f'{url}/{instance.external_id}', headers=headers)
                response.raise_for_status()

                data = response.json()
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
                return

            if 'given_name' in attribute_map:
                attribute = Attribute.objects.get(uri=attribute_map['given_name'])
                if question := find_question(catalog, attribute):
                    if value_set := find_set(answer_tree, question, instance):
                        Value.objects.update_or_create(
                            project=instance.project,
                            snapshot=None,
                            attribute=Attribute.objects.get(uri=attribute_map['given_name']),
                            set_prefix=value_set.get('set_prefix'),
                            set_index=value_set.get('set_index'),
                            defaults={
                                'text': dpath.get(data, '/person/name/given-names/value'),
                            },
                        )

            if 'family_name' in attribute_map:
                attribute = Attribute.objects.get(uri=attribute_map['family_name'])
                if question := find_question(catalog, attribute):
                    if value_set := find_set(answer_tree, question, instance):
                        Value.objects.update_or_create(
                            project=instance.project,
                            snapshot=None,
                            attribute=Attribute.objects.get(uri=attribute_map['family_name']),
                            set_prefix=value_set.get('set_prefix'),
                            set_index=value_set.get('set_index'),
                            defaults={
                                'text': dpath.get(data, '/person/name/family-name/value'),
                            },
                        )

            if 'affiliation_name' in attribute_map:
                attribute = Attribute.objects.get(uri=attribute_map['affiliation_name'])
                if question := find_question(catalog, attribute):
                    texts = get_affiliation_names(data)
                    save_affiliation_values(instance, catalog, answer_tree, attribute, question, texts)

            if 'affiliation_ror' in attribute_map:
                attribute = Attribute.objects.get(uri=attribute_map['affiliation_ror'])
                if question := find_question(catalog, attribute):
                    texts = get_affiliation_rors(data)
                    save_affiliation_values(instance, catalog, answer_tree, attribute, question, texts)


def save_affiliation_values(instance, catalog, answer_tree, attribute, question, texts):
    parent = find_parent(catalog, question)

    if question.is_collection:
        # the question is a collection: every affiliation gets its own collection_index
        if value_set := find_set(answer_tree, question, instance):
            for collection_index, text in enumerate(texts):
                if text:
                    Value.objects.update_or_create(
                        project=instance.project,
                        snapshot=None,
                        attribute=attribute,
                        set_prefix=value_set.get('set_prefix'),
                        set_index=value_set.get('set_index'),
                        collection_index=collection_index,
                        defaults={
                            'text': text,
                        },
                    )

            # delete surplus collection_indexes
            Value.objects.filter(
                project=instance.project,
                snapshot=None,
                set_prefix=value_set.get('set_prefix'),
                set_index=value_set.get('set_index'),
                attribute=attribute,
            ).exclude(
                collection_index__in=range(len(texts)),
            ).delete()

    elif parent and parent.is_collection:
        # the parent is a collection: every affiliation gets its own set of the parent,
        # we look for the set containing the parent, since the parent might not have any sets yet
        if value_set := find_set(answer_tree, parent, instance):
            for set_index, text in enumerate(texts):
                if text:
                    Value.objects.update_or_create(
                        project=instance.project,
                        snapshot=None,
                        attribute=attribute,
                        set_prefix=get_child_prefix(value_set),
                        set_index=set_index,
                        defaults={
                            'text': text,
                        },
                    )

    else:
        # neither is a collection: only the first affiliation is stored
        if value_set := find_set(answer_tree, question, instance):
            if texts and texts[0]:
                Value.objects.update_or_create(
                    project=instance.project,
                    snapshot=None,
                    attribute=attribute,
                    set_prefix=value_set.get('set_prefix'),
                    set_index=value_set.get('set_index'),
                    defaults={
                        'text': texts[0],
                    },
                )


def get_affiliation_names(data):
    affiliations = []
    for affiliation in dpath.get(data, '/activities-summary/employments/affiliation-group'):
        for summary in affiliation.get('summaries'):
            if dpath.get(summary, '/employment-summary/end-date') is None:
                affiliations.append(get_affiliation_name(summary))
    return affiliations


def get_affiliation_name(summary):
    return dpath.get(summary, '/employment-summary/organization/name')


def get_affiliation_rors(data):
    affiliations = []
    for affiliation in dpath.get(data, '/activities-summary/employments/affiliation-group'):
        for summary in affiliation.get('summaries'):
            if dpath.get(summary, '/employment-summary/end-date') is None:
                affiliations.append(get_affiliation_ror(summary))
    return affiliations


def get_affiliation_ror(summary):
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
        return disambiguation_id.replace('https://ror.org/', '')
    elif disambiguation_source == 'RINGGOLD':
        return search_wikidata(disambiguation_id)
    elif disambiguation_source in ['GRID', 'FUNDREF']:
        return search_ror(disambiguation_id)
    else:
        return None


def search_wikidata(ringgold_id):
    url = getattr(settings, 'WIKIDATA_PROVIDER_URL', 'https://www.wikidata.org/w/api.php')
    headers = getattr(settings, 'WIKIDATA_PROVIDER_HEADERS', {})

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

    try:
        entity = dpath.get(entity_response_data, '/query/search/0/title')
    except KeyError:
        return None

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

    try:
        return dpath.get(ror_response_data, '/claims/P6782/0/mainsnak/datavalue/value')
    except KeyError:
        return None


def search_ror(disambiguation_id):
    url = getattr(settings, 'ROR_PROVIDER_URL', 'https://api.ror.org/v2/').rstrip('/')
    headers = getattr(settings, 'ROR_PROVIDER_HEADERS', {})
    response = requests.get(
        f'{url}/organizations',
        params={'query': disambiguation_id},
        headers=headers,
    )
    response.raise_for_status()
    response_data = response.json()

    try:
        return dpath.get(response_data, '/items/0/id').replace('https://ror.org/', '')
    except KeyError:
        return None
