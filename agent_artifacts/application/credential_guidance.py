"""What a credential is and how to get one, said the same way wherever it is asked for (D-263).

An author declares a secret input's human name, purpose, acquisition instruction and format in its
`help` (§154, INV-168). Installation asks for that value in three places: screen 07's form, the
terminal lent to the provider's own prompt, and the CLI's refusal for an unanswered credential.
This module is the one place those words are made, so the three cannot drift or say less than the
author wrote.

Several artifacts may need the same credential. They are grouped by what they say: owners with
identical help share one explanation, and owners whose help differs each keep their own, so no
instruction is dropped and none is attributed to the wrong artifact.

It is metadata only. Nothing here chooses a provider, binds a reference, validates a value or holds
one, and an artifact that says nothing gets an honest fallback rather than an invented link.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from agent_artifacts.domain.inputs import InputGuidance, RuntimeInput, SecretInput

__all__ = [
    "CredentialGuidance",
    "credential_guidance_lines",
    "credential_guidance_to_data",
    "credential_prompt_briefing",
    "gather_credential_guidance",
    "guidance_by_input",
]


@dataclass(frozen=True, slots=True)
class CredentialGuidance:
    """What one or more owners say about a credential they need. It never holds a value."""

    owners: tuple[str, ...]
    label: str
    description: str = ""
    obtain_label: str | None = None
    obtain_url: str | None = None
    format_hint: str | None = None
    validation_hint: str = ""

    def __post_init__(self) -> None:
        if (
            any(not isinstance(item, str) or not item for item in self.owners)
            or not isinstance(self.label, str)
            or not self.label
            or (self.obtain_url is not None and self.obtain_label is None)
        ):
            raise ValueError("credential guidance is invalid")

    @property
    def guided(self) -> bool:
        """Whether the author said how to obtain the value; a description alone does not."""

        return self.obtain_label is not None


def _explanation(input_id: str, guidance: InputGuidance | None) -> tuple:
    if guidance is None:
        return (input_id, "", None, None, None, "")
    obtain = guidance.obtain_from
    return (
        guidance.label,
        guidance.description,
        None if obtain is None else obtain.label,
        None if obtain is None else obtain.url,
        # A secret's example is never shown: §156.1/INV-168 keep plausible values out of help.
        guidance.format_hint,
        guidance.validation_hint,
    )


def gather_credential_guidance(
    input_id: str, declared: Iterable[tuple[str, InputGuidance | None]]
) -> tuple[CredentialGuidance, ...]:
    """Group what each owner declares about one credential, keeping every owner exactly once.

    Groups are ordered by their first owner and owners within a group by name, so the same
    declarations always read the same way. An empty owner is a declaration nobody named (a caller
    that only has the input); it explains the credential without saying who needs it. With no
    declarations at all the credential is still named, by its input id, and reads as unguided.
    """

    explained: dict[tuple, set[str]] = {}
    for owner, guidance in declared:
        explained.setdefault(_explanation(input_id, guidance), set()).add(owner)
    if not explained:
        return (CredentialGuidance((), input_id),)
    groups = []
    claimed: set[str] = set()
    for explanation, owners in explained.items():
        # An owner declares one input once; were it to appear twice, it stays with the first
        # explanation it gave rather than being named under two.
        mine = owners - claimed
        claimed.update(mine)
        if mine:
            groups.append(CredentialGuidance(tuple(sorted(mine - {""})), *explanation))
    return tuple(sorted(groups, key=lambda group: group.owners))


def guidance_by_input(
    declared_by: Iterable[tuple[str, RuntimeInput]],
) -> dict[str, tuple[CredentialGuidance, ...]]:
    """Every secret input's guidance, keyed by input id, from (owner, declaration) pairs."""

    collected: dict[str, list[tuple[str, InputGuidance | None]]] = {}
    for owner, item in declared_by:
        if isinstance(item, SecretInput):
            collected.setdefault(item.id.value, []).append((owner, item.guidance))
    return {key: gather_credential_guidance(key, value) for key, value in collected.items()}


def _owners(group: CredentialGuidance) -> str:
    return ", ".join(group.owners)


def credential_guidance_lines(groups: tuple[CredentialGuidance, ...]) -> tuple[str, ...]:
    """The explanation a person reads before entering the credential, in Fast as well as Verbose."""

    lines: list[str] = []
    for group in groups:
        lines.append(f"{group.label} — needed by {_owners(group)}" if group.owners else group.label)
        if group.description:
            lines.append(f"  {group.description}")
        if group.obtain_label is not None:
            link = "" if group.obtain_url is None else f" → {group.obtain_url}"
            lines.append(f"  Get it: {group.obtain_label}{link}")
        else:
            maintainer = _owners(group) or "the artifact that needs it"
            lines.append(f"  Where to get it is not stated; ask the maintainer of {maintainer}.")
        if group.format_hint:
            lines.append(f"  Format: {group.format_hint}")
        if group.validation_hint:
            lines.append(f"  {group.validation_hint}")
    return tuple(lines)


def credential_prompt_briefing(
    groups: tuple[CredentialGuidance, ...], *, provider: str, replacing: bool = False
) -> tuple[str, ...]:
    """What is written on the lent terminal immediately before the provider asks for the value."""

    if not isinstance(provider, str) or not provider:
        raise ValueError("a credential briefing names the provider that asks")
    heading = (
        "AART is replacing a credential." if replacing else "AART needs a credential to continue."
    )
    asks = "the new value" if replacing else "it"
    return (
        heading,
        *credential_guidance_lines(groups),
        f"{provider} asks for {asks} next. Type it there; AART never sees or keeps it.",
    )


def credential_guidance_to_data(groups: tuple[CredentialGuidance, ...]) -> list[dict[str, object]]:
    return [
        {
            "owners": list(group.owners),
            "label": group.label,
            "description": group.description,
            "obtain_from": (
                None
                if group.obtain_label is None
                else {"label": group.obtain_label, "url": group.obtain_url}
            ),
            "format_hint": group.format_hint,
            "validation_hint": group.validation_hint,
        }
        for group in groups
    ]
