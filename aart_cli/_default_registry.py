"""Default Registry this package was built with.

Generated at build time by ``scripts/inject_default_registry.py`` from the release variable
``AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL``, which holds ``<alias>=<url>``.

Both values are empty here and must stay empty in the source tree. Empty means the build baked no
default: the public build's state, and not an error. A real address committed here would make one
deployment's Registry the default for every fork of this project, which is the mistake D-309
removed from the release workflow.

Read this module through ``aart_cli.configuration.seed``, never directly. It is a default rather
than a restriction: it says where a first run starts, never what a person is allowed to connect.
"""

ALIAS = ""
URL = ""
