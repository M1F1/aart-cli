"""The telemetry server this package sends to (§213).

Generated at build time by ``scripts/inject_default_telemetry.py`` from the release variable
``AART_CLI_TELEMETRY_ENDPOINT``: a server's base address, such as ``https://telemetry.example.com``.

Empty here, and it must stay empty in the source tree. Empty names no server: telemetry is then
turned on only with an address given. A baked address turns telemetry on at a home's first start
where nobody turned it on or off, and it then sends Activity's history too (D-503, D-505).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""

ENDPOINT = ""
