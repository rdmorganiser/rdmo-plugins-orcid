rdmo-plugins-orcid
==================

This plugin implements dynamic option set, that queries the expanded-search endpoint of the [ORCID public API](https://info.orcid.org/documentation/api-tutorials/api-tutorial-searching-the-orcid-registry/).


Setup
-----

Install the plugin in your RDMO virtual environment using pip (directly from GitHub):

```bash
pip install git+https://github.com/rdmorganiser/rdmo-plugins-orcid
```

Add the `rdmo_orcid` app to `INSTALLED_APPS` and the plugin to `OPTIONSET_PROVIDERS` in `config/settings/local.py`:

```python
INSTALLED_APPS += ['rdmo_orcid']

...

OPTIONSET_PROVIDERS += [
    ('orcid', _('ORCID Provider'), 'rdmo_orcid.providers.OrcidProvider')
]
```

The option set provider should now be selectable for option sets in your RDMO installation. For a minimal example catalog, see the files in `xml`.

If a selection of a ORCIDiD should update other fields, you can add a `ORCID_PROVIDER_MAP` in your settings, e.g.:

```python
ORCID_PROVIDER_MAP = [
    {
        'orcid': 'https://rdmorganiser.github.io/terms/domain/project/dataset/creator/orcid',
        'given_name': 'https://rdmorganiser.github.io/terms/domain/project/dataset/creator/given_name',
        'family_name': 'https://rdmorganiser.github.io/terms/domain/project/dataset/creator/family_name',
        'affiliation': 'https://rdmorganiser.github.io/terms/domain/project/dataset/creator/affiliation',
    }
]
```

In this case, a change to the identifier of a coordinator (`https://rdmorganiser.github.io/terms/domain/project/dataset/creator/orcid`) will update their name (`https://rdmorganiser.github.io/terms/domain/project/dataset/creator/given_name`) automatically. `ORCID_PROVIDER_MAP` is a list of mappings, since multiple ORCIDiD could be used and should update different other values. The question for `affiliation` should be a collection since ORCID will often return one than more current affiliation.

While not required, you can add a custom `User-Agent` to your requests so that the provider can perform statistical analyses and, if you add an email address, might contact you. This can be done by adding the following to your settings.

```python
ORCID_PROVIDER_HEADERS = {
    'User-Agent': 'rdmo.example.com/1.0 (mail@rdmo.example.com) rdmo-plugins-orcid/1.0'
}
```
