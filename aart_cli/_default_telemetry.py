"""The telemetry server this package sends to, and whether it sends uses it did not install (§213).

Generated at build time by ``scripts/inject_default_telemetry.py`` from the release variables
``AART_CLI_TELEMETRY_ENDPOINT``: a server's base address, such as ``https://telemetry.example.com``;
and ``AART_CLI_TELEMETRY_UNMANAGED_USES``: ``on`` or ``off``.

Both are empty here, and must stay empty in the source tree. An empty address names no server:
telemetry is then turned on only with an address given. A baked address turns telemetry on at a
home's first start where nobody turned it on or off, and it then sends Activity's history too
(D-503, D-505). An empty ``UNMANAGED_USES`` sends uses of skills and MCPs aart-cli did not install,
by name, until a person chooses otherwise in Settings; ``off`` does not (D-508).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""

ENDPOINT = ""
UNMANAGED_USES = ""
