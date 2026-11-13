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
        'affiliation_name': 'https://rdmorganiser.github.io/terms/domain/project/dataset/creator/affiliation/name',
        'affiliation_ror': 'https://rdmorganiser.github.io/terms/domain/project/dataset/creator/affiliation/ror',
    },
]
```

In this case, a change to the identifier of a coordinator (`https://rdmorganiser.github.io/terms/domain/project/dataset/creator/orcid`) will update their name (`https://rdmorganiser.github.io/terms/domain/project/dataset/creator/given_name`) automatically. `ORCID_PROVIDER_MAP` is a list of mappings, since multiple ORCIDiD could be used and should update different other values.

`affiliation_name` and `affiliation_ror` are filled with the names and the [ROR IDs](https://ror.org) of the current employments in the ORCID record. Since ORCID will often return more than one current affiliation, they are stored depending on the catalog:

* If the question is a collection, every affiliation is stored as a separate value.
* If the question is in a question set which is a collection (and the ORCID question is not), every affiliation is stored in a separate set.
* Otherwise, only the first affiliation is stored.

The ROR ID is taken from the disambiguated organization of the employment in the ORCID record. Depending on the source of the identifier, it is obtained as follows:

* **ROR**: the ID is used directly.
* **GRID** and **FundRef**: the ID is searched using the [ROR API](https://ror.readme.io/) and the ROR ID of the first result is used.
* **Ringgold**: the item with this Ringgold ID ([P3500](https://www.wikidata.org/wiki/Property:P3500)) is searched in [Wikidata](https://www.wikidata.org) and its ROR ID ([P6782](https://www.wikidata.org/wiki/Property:P6782)) is used.

If the organization has no identifier, or the lookup fails, no ROR ID is stored for this affiliation. Since the [Wikidata User-Agent policy](https://meta.wikimedia.org/wiki/User-Agent_policy) requires a `User-Agent`, the lookup in Wikidata is only performed if a `User-Agent` is configured in `ORCID_PROVIDER_HEADERS` (see below).

While not required, you can add a custom `User-Agent` to your requests so that the providers can perform statistical analyses and, if you add an email address, might contact you. This can be done by adding the following to your settings. The headers are used for the requests to ORCID, ROR, and Wikidata.

```python
ORCID_PROVIDER_HEADERS = {
    'User-Agent': 'rdmo.example.com/1.0 (mail@rdmo.example.com) rdmo-plugins-orcid/1.0'
}
```

The handler which updates the other values can be customized by creating a subclass of `rdmo_orcid.handlers.OrcidHandler` and adding its python dot path to your settings, e.g.:

```python
ORCID_HANDLER = 'my_app.handlers.MyOrcidHandler'
```
