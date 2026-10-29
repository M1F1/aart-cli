"""The telemetry server this package offers when a person turns telemetry on (§213).

Generated at build time by ``scripts/inject_default_telemetry.py`` from the release variable
``AART_CLI_TELEMETRY_ENDPOINT``: a server's base address, such as ``https://telemetry.example.com``.

Empty here, and it must stay empty in the source tree. Empty offers no server: telemetry is then
turned on only with an address given. A baked address alone sends nothing; telemetry stays off
until a person turns it on (D-503).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""

ENDPOINT = ""
