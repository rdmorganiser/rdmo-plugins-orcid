from django.apps import AppConfig


class RDMOOrcidConfig(AppConfig):
    name = 'rdmo_orcid'
    verbose_name = 'ORCID Plugin'

    def ready(self):
        from . import handlers  # noqa: F401
