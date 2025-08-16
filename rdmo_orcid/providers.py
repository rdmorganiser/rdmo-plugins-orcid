import re

from django.conf import settings
from django.templatetags.static import static

import requests

from rdmo.options.providers import Provider


class OrcidProvider(Provider):

    search = True
    refresh = True

    def get_options(self, project, search=None, user=None, site=None):
        if search:
            url = getattr(settings, 'ORCID_PROVIDER_URL', 'https://pub.orcid.org/v3.0/').rstrip('/')
            headers = getattr(settings, 'ORCID_PROVIDER_HEADERS', {})
            headers['Accept'] = 'application/json'

            response = requests.get(url + '/expanded-search/', params={
                'q': self.get_search(search),
                'start': 0,
                'rows': 10
            }, headers=headers)

            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                pass
            else:
                if data.get('expanded-result'):
                    return [
                        {
                            'id': item['orcid-id'],
                            'text': self.get_text(item)
                        } for item in data['expanded-result']
                    ]

        # return an empty list by default
        return []

    def get_text(self, item):
        orcid_id = item['orcid-id']
        orcid_img = static('accounts/img/orcid_16x16.png')
        orcid_link = f'<a href="https://orcid.org/{orcid_id}"><img src="{orcid_img}" alt="orcid logo" /></a>'
        text = '{given-names} {family-names} {orcid_link}'.format(**item, orcid_link=orcid_link)
        if item.get('institution-name'):
            institutions = ', '.join(item['institution-name'][:2])
            text += f' ({institutions})'
        return text

    def get_search(self, search):
        # reverse get_text to perform the search, remove everything after ( or [
        match = re.match(r'^[^([]+', search)
        if match:
            tokens = match[0].split()
        else:
            tokens = search.split()

        return '+AND+'.join(tokens)
