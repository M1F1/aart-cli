"""Complete, read-only offer disclosure for Marketplace's More info region."""

from aart_cli.application.consumer_views import ConfigInputView, CredentialInputView
from aart_cli.application.credential_guidance import credential_guidance_lines
from aart_cli.redaction import redact_text
from aart_cli.tui_layout import CONTENT_MEASURE, field_block, separate, wrap_lines
from aart_cli.tui_marketplace import MarketplaceArtifactRow, render_artifact_detail


def _input_guidance(view: ConfigInputView | CredentialInputView) -> tuple[str, ...]:
    fields = [
        ("Input", f"{view.label} ({view.id})"),
        ("Type", "Configuration" if isinstance(view, ConfigInputView) else "Credential"),
        ("Declared required", "yes" if view.required else "no"),
        ("Binding", f"{view.binding} ({view.exposure})"),
        ("Description", view.description),
    ]
    if view.format_hint:
        fields.append(("Format", view.format_hint))
    if view.obtain_from:
        fields.append(("Get from", view.obtain_from[0]))
        if view.obtain_from[1]:
            fields.append(("Guide", view.obtain_from[1]))
    if isinstance(view, ConfigInputView):
        if view.example:
            fields.append(("Example", view.example))
        if view.validation_hint:
            fields.append(("Validation", view.validation_hint))
        if view.default is not None:
            fields.append(("Declared default", view.default))
    return separate(
        field_block(tuple(fields), indent=2, width=CONTENT_MEASURE),
        credential_guidance_lines(view.guidance) if isinstance(view, CredentialInputView) else (),
    )


def artifact_disclosure(
    row: MarketplaceArtifactRow, inputs: tuple[ConfigInputView | CredentialInputView, ...] = ()
) -> tuple[str, ...]:
    identity = field_block(
        (
            ("Artifact", row.key),
            ("Kind", row.identity.kind.capitalize()),
            ("Version", row.version),
            ("Registry", str(row.source_alias)),
            *((("Upstream", redact_text(row.upstream)),) if row.upstream else ()),
            ("Description", row.summary.strip() or "No description was approved for this offer."),
        ),
        indent=2,
        width=CONTENT_MEASURE,
    )
    evidence = render_artifact_detail(row, include_identity=False)
    guidance = separate(*(_input_guidance(view) for view in inputs))
    return wrap_lines(separate(identity, evidence, guidance), width=CONTENT_MEASURE)
