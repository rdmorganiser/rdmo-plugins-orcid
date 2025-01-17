from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

import dpath
import requests

from rdmo.domain.models import Attribute
from rdmo.projects.models import Value


@receiver(post_save, sender=Value)
def orcid_handler(sender, request=None, instance=None, **kwargs):
    # check for ORCID_PROVIDER_MAP
    if not getattr(settings, 'ORCID_PROVIDER_MAP', None):
        return

    # check if we are importing fixtures
    if kwargs.get('raw'):
        return

    # check if this value instance has an external_id
    if not instance.external_id:
        return

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
                Value.objects.update_or_create(
                    project=instance.project,
                    attribute=Attribute.objects.get(uri=attribute_map['given_name']),
                    set_prefix=instance.set_prefix,
                    set_index=instance.set_index,
                    defaults={
                        'text': dpath.get(data, '/person/name/given-names/value')
                    }
                )

            if 'family_name' in attribute_map:
                Value.objects.update_or_create(
                    project=instance.project,
                    attribute=Attribute.objects.get(uri=attribute_map['family_name']),
                    set_prefix=instance.set_prefix,
                    set_index=instance.set_index,
                    defaults={
                        'text': dpath.get(data, '/person/name/family-name/value')
                    }
                )

            if 'affiliation' in attribute_map:
                attribute = Attribute.objects.get(uri=attribute_map['affiliation'])

                affiliations = []
                for affiliation in dpath.get(data, '/activities-summary/employments/affiliation-group'):
                    for summaries in affiliation.get('summaries'):
                        if dpath.get(summaries, '/employment-summary/end-date') is None:
                            affiliations.append(dpath.get(summaries, '/employment-summary/organization/name'))

                for collection_index, affiliation in enumerate(affiliations):
                    Value.objects.update_or_create(
                        project=instance.project,
                        attribute=attribute,
                        set_prefix=instance.set_prefix,
                        set_index=instance.set_index,
                        collection_index=collection_index,
                        defaults={
                            'text': affiliation
                        }
                    )

                # delete surplus collection_indexes
                Value.objects.filter(
                    project=instance.project,
                    snapshot=None,
                    set_prefix=instance.set_prefix,
                    set_index=instance.set_index,
                    attribute=attribute
                ).exclude(collection_index__in=range(len(affiliations))).delete()
