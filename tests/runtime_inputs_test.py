"""CP-08 runtime input separation, binding independence and credential-mutation planning."""

from __future__ import annotations

import ast
import dataclasses
import json
import unittest
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.credential_lifecycle import (
    CREDENTIAL_DEPENDANTS,
    CREDENTIAL_POLICY_VIOLATION,
    plan_credential_mutation,
)
from agent_artifacts.application.input_binding import (
    INPUT_BINDING_INVALID,
    INPUT_POLICY_VIOLATION,
    INPUT_REQUIRED,
    bind_runtime_inputs,
)
from agent_artifacts.domain.credentials import (
    CredentialIntent,
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
    credential_reference_to_data,
)
from agent_artifacts.domain.effects import (
    DeleteCredential,
    ReplaceCredential,
    RiskClass,
    StoreCredential,
    VerifyCredential,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
)
from agent_artifacts.domain.inputs import (
    CliArgumentBinding,
    ConfigInput,
    EnvironmentBinding,
    FileBinding,
    InputGuidance,
    InputId,
    InputValidation,
    ObtainFrom,
    PersistedConfigValue,
    PolicyProvidedValue,
    PromptedConfigValue,
    SecretInput,
    SecretProviderReference,
    StdinBinding,
    bound_inputs_to_data,
    input_to_data,
    validate_config_value,
)
from agent_artifacts.domain.policies import EffectivePolicy, PolicyOverlay, compose_policy
from agent_artifacts.domain.result import Err, Ok
from tests.credential_fixtures import credential_url

PROVIDER = CredentialProviderRef("macos-keychain", "company.forge", "agent")
HOST = InputId("forge-host")
USER = InputId("user-id")
CREDENTIAL = InputId("forge-credential")


def _coordinate(name: str) -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("company-core"), ArtifactIdentity("mcp", name), "1.0.0")


def _secret() -> SecretInput:
    return SecretInput(CREDENTIAL, StdinBinding())


def _reference() -> CredentialReference:
    return CredentialReference(CREDENTIAL, PROVIDER)


class RuntimeInputAlgebraTest(unittest.TestCase):
    def test_secret_and_config_stay_distinct_types_with_distinct_persistence_rules(self) -> None:
        secret = _secret()
        config = ConfigInput(HOST, CliArgumentBinding("--forge-host"))

        self.assertNotIsInstance(secret, ConfigInput)
        self.assertNotIsInstance(config, SecretInput)
        self.assertEqual(input_to_data(secret)["kind"], "secret")
        self.assertEqual(input_to_data(config)["kind"], "config")
        # No field on either type can carry a value for a secret.
        secret_fields = {field.name for field in dataclasses.fields(SecretInput)}
        self.assertNotIn("value", secret_fields)
        self.assertNotIn("default", secret_fields)

    def test_binding_is_independent_of_value_source(self) -> None:
        bindings = (
            CliArgumentBinding("--forge-credential"),
            EnvironmentBinding("FORGE_CREDENTIAL"),
            FileBinding("/run/secrets/forge"),
            StdinBinding(),
        )
        for binding in bindings:
            with self.subTest(binding=type(binding).__name__):
                bound = bind_runtime_inputs(
                    (SecretInput(CREDENTIAL, binding),),
                    (SecretProviderReference(CREDENTIAL, PROVIDER),),
                    EffectivePolicy(),
                )
                self.assertIsInstance(bound, Ok)
                self.assertEqual(bound.value.inputs[0].binding, binding)
                self.assertEqual(bound.value.credential_references, (_reference(),))

    def test_cli_and_environment_bindings_declare_weaker_exposure_than_stdin(self) -> None:
        self.assertGreater(
            CliArgumentBinding("--forge-credential").exposure,
            StdinBinding().exposure,
        )
        self.assertGreater(
            EnvironmentBinding("FORGE_CREDENTIAL").exposure,
            FileBinding("/run/secrets/forge").exposure,
        )

    def test_secret_guidance_refuses_example_values_and_credential_shapes(self) -> None:
        allowed = SecretInput(
            CREDENTIAL,
            StdinBinding(),
            guidance=InputGuidance(
                label="Forge credential",
                description="Used to authenticate to the internal forge.",
                format_hint="prefix followed by opaque characters",
                obtain_from=ObtainFrom("Create one", "https://forge.example/settings"),
            ),
        )
        self.assertIsNone(allowed.guidance.example)

        with self.assertRaises(ValueError):
            SecretInput(
                CREDENTIAL,
                StdinBinding(),
                guidance=InputGuidance(label="Forge credential", example="anything at all"),
            )

    def test_config_guidance_may_carry_concrete_examples(self) -> None:
        config = ConfigInput(
            USER,
            CliArgumentBinding("--user-id"),
            guidance=InputGuidance(label="User ID", example="pl847362"),
        )
        self.assertEqual(config.guidance.example, "pl847362")

    def test_validation_is_authoritative_and_guidance_only_explains_it(self) -> None:
        config = ConfigInput(
            HOST,
            CliArgumentBinding("--forge-host"),
            validation=InputValidation(kind="url", allowed_hosts=("forge.example",)),
            guidance=InputGuidance(label="Forge URL", validation_hint="Use the company forge."),
        )
        guidance_fields = {field.name for field in dataclasses.fields(InputGuidance)}
        self.assertNotIn("allowed_hosts", guidance_fields)
        self.assertNotIn("pattern", guidance_fields)

        rejected = bind_runtime_inputs(
            (config,),
            (PersistedConfigValue(HOST, "https://forge.invalid"),),
            EffectivePolicy(),
        )
        self.assertIsInstance(rejected, Err)
        self.assertEqual(rejected.diagnostics[0].code, INPUT_BINDING_INVALID)

        accepted = bind_runtime_inputs(
            (config,),
            (PersistedConfigValue(HOST, "https://forge.example/api"),),
            EffectivePolicy(),
        )
        self.assertIsInstance(accepted, Ok)

    def test_host_allow_listing_refuses_every_url_it_cannot_read_plainly(self) -> None:
        # A host allow-list is only as good as the agreement between the checker and whatever
        # opens the URL later. Anything a lenient parser would resolve differently is refused
        # rather than interpreted, so the two can never disagree.
        validation = InputValidation(kind="url", allowed_hosts=("forge.example",))
        accepted = (
            "https://forge.example",
            "https://forge.example/api/v1",
            "https://forge.example:8443/api",
            "https://FORGE.EXAMPLE/api",
            "http://forge.example?q=1",
        )
        refused = (
            "https://other.example/",  # A host that is simply not on the list.
            # Userinfo: the classic allow-list bypass, assembled rather than written down so
            # `scripts/secret_shape_check.py` stays able to run over its own repository.
            credential_url("forge.example", "/"),
            "https://forge.example\\@other.example/",  # A backslash read as a separator.
            "https://other.example#@forge.example/",  # The allowed host in the fragment only.
            "https://forge.example\x00.other.example/",  # A NUL truncating a later reader.
            "https://forge.example\n/",  # A newline splitting a later request.
            "ftp://forge.example/",  # A scheme that is not http(s).
            "//forge.example/",  # No scheme at all.
            "https://[::1]/",  # An address literal, which the list cannot name.
            "https://forge.example:notaport/",  # A port that is not a number.
            "https://.forge.example/",  # A leading label separator.
            "https://forge.example./",  # A trailing root dot.
            "https://forge..example/",  # An empty label.
            "",
        )
        for value in accepted:
            with self.subTest(accepted=value):
                self.assertIsNone(validate_config_value(validation, value))
        for value in refused:
            with self.subTest(refused=value):
                self.assertIsNotNone(validate_config_value(validation, value))

    def test_url_validation_holds_no_import_that_could_reach_a_network(self) -> None:
        source = (
            Path(__file__).resolve().parent.parent / "agent_artifacts" / "domain" / "inputs.py"
        ).read_text(encoding="utf-8")
        roots = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".", 1)[0])
        self.assertEqual(roots & {"urllib", "socket", "http", "ssl"}, set())


class InputBindingTest(unittest.TestCase):
    def test_a_secret_input_can_only_bind_to_a_provider_reference(self) -> None:
        for source in (
            PersistedConfigValue(CREDENTIAL, "value"),
            PromptedConfigValue(CREDENTIAL, "value"),
            PolicyProvidedValue(CREDENTIAL, "value"),
        ):
            with self.subTest(source=type(source).__name__):
                bound = bind_runtime_inputs((_secret(),), (source,), EffectivePolicy())
                self.assertIsInstance(bound, Err)
                self.assertEqual(bound.diagnostics[0].code, INPUT_BINDING_INVALID)

    def test_a_config_input_cannot_bind_to_a_secret_provider(self) -> None:
        bound = bind_runtime_inputs(
            (ConfigInput(HOST, CliArgumentBinding("--forge-host")),),
            (SecretProviderReference(HOST, PROVIDER),),
            EffectivePolicy(),
        )
        self.assertIsInstance(bound, Err)
        self.assertEqual(bound.diagnostics[0].code, INPUT_BINDING_INVALID)

    def test_a_missing_required_input_fails_and_an_optional_one_does_not(self) -> None:
        missing = bind_runtime_inputs((_secret(),), (), policy=EffectivePolicy())
        self.assertIsInstance(missing, Err)
        self.assertEqual(missing.diagnostics[0].code, INPUT_REQUIRED)

        optional = bind_runtime_inputs(
            (ConfigInput(USER, CliArgumentBinding("--user-id"), required=False),),
            (),
            EffectivePolicy(),
        )
        self.assertIsInstance(optional, Ok)
        self.assertEqual(optional.value.inputs, ())

    def test_policy_restricts_secret_providers_and_secret_bindings(self) -> None:
        forbidden_provider = bind_runtime_inputs(
            (_secret(),),
            (SecretProviderReference(CREDENTIAL, PROVIDER),),
            policy=EffectivePolicy(allowed_credential_providers=frozenset({"enterprise-vault"})),
        )
        self.assertIsInstance(forbidden_provider, Err)
        self.assertEqual(forbidden_provider.diagnostics[0].code, INPUT_POLICY_VIOLATION)

        forbidden_binding = bind_runtime_inputs(
            (SecretInput(CREDENTIAL, CliArgumentBinding("--forge-credential")),),
            (SecretProviderReference(CREDENTIAL, PROVIDER),),
            policy=EffectivePolicy(allowed_secret_bindings=frozenset({"stdin"})),
        )
        self.assertIsInstance(forbidden_binding, Err)
        self.assertEqual(forbidden_binding.diagnostics[0].code, INPUT_POLICY_VIOLATION)

    def test_policy_can_forbid_persisting_one_named_config_input(self) -> None:
        policy = EffectivePolicy(forbidden_persisted_config=frozenset({"user-id"}))
        config = ConfigInput(USER, CliArgumentBinding("--user-id"))

        persisted = bind_runtime_inputs(
            (config,), (PersistedConfigValue(USER, "pl847362"),), policy
        )
        self.assertIsInstance(persisted, Err)
        self.assertEqual(persisted.diagnostics[0].code, INPUT_POLICY_VIOLATION)

        prompted = bind_runtime_inputs((config,), (PromptedConfigValue(USER, "pl847362"),), policy)
        self.assertIsInstance(prompted, Ok)

    def test_bound_projection_carries_references_and_config_but_never_a_secret(self) -> None:
        bound = bind_runtime_inputs(
            (_secret(), ConfigInput(HOST, CliArgumentBinding("--forge-host"))),
            (
                SecretProviderReference(CREDENTIAL, PROVIDER),
                PersistedConfigValue(HOST, "https://forge.example"),
            ),
            EffectivePolicy(),
        )
        self.assertIsInstance(bound, Ok)
        data = bound_inputs_to_data(bound.value)
        rendered = json.dumps(data, sort_keys=True)

        self.assertIn("https://forge.example", rendered)
        self.assertIn("macos-keychain", rendered)
        self.assertEqual(bound.value.config_values, ((HOST, "https://forge.example"),))
        self.assertEqual(bound.value.credential_references, (_reference(),))
        # The secret input contributes identity and provider only.
        secret_entry = next(item for item in data["inputs"] if item["id"] == CREDENTIAL.value)
        self.assertEqual(set(secret_entry["source"]), {"kind", "provider"})


class CredentialLifecycleTest(unittest.TestCase):
    def test_storing_an_absent_credential_plans_store_then_verify(self) -> None:
        observation = CredentialObservation(
            _reference(), ProviderState.AVAILABLE, CredentialState.ABSENT
        )
        plan = plan_credential_mutation(
            CredentialIntent.STORE, observation, policy=EffectivePolicy()
        )

        self.assertIsInstance(plan, Ok)
        self.assertEqual(
            tuple(type(effect) for effect in plan.value.effects),
            (StoreCredential, VerifyCredential),
        )
        self.assertEqual(plan.value.dependants, ())
        self.assertFalse(plan.value.requires_acknowledgement)

    def test_storing_over_a_present_credential_requires_explicit_replacement(self) -> None:
        observation = CredentialObservation(
            _reference(), ProviderState.AVAILABLE, CredentialState.PRESENT
        )
        kept = plan_credential_mutation(
            CredentialIntent.STORE, observation, policy=EffectivePolicy()
        )
        self.assertIsInstance(kept, Err)

        replaced = plan_credential_mutation(
            CredentialIntent.REPLACE, observation, (), policy=EffectivePolicy()
        )
        self.assertIsInstance(replaced, Ok)
        self.assertEqual(
            tuple(type(effect) for effect in replaced.value.effects),
            (ReplaceCredential, VerifyCredential),
        )

    def test_replacement_and_deletion_surface_every_dependant(self) -> None:
        observation = CredentialObservation(
            _reference(), ProviderState.AVAILABLE, CredentialState.PRESENT
        )
        dependants = (_coordinate("review"), _coordinate("forge"))

        replaced = plan_credential_mutation(
            CredentialIntent.REPLACE, observation, dependants, policy=EffectivePolicy()
        )
        self.assertIsInstance(replaced, Ok)
        self.assertEqual(replaced.value.dependants, (_coordinate("forge"), _coordinate("review")))
        self.assertTrue(replaced.value.requires_acknowledgement)

        deleted = plan_credential_mutation(
            CredentialIntent.DELETE, observation, dependants, policy=EffectivePolicy()
        )
        self.assertIsInstance(deleted, Err)
        self.assertEqual(deleted.diagnostics[0].code, CREDENTIAL_DEPENDANTS)

        acknowledged = plan_credential_mutation(
            CredentialIntent.DELETE,
            observation,
            dependants,
            policy=EffectivePolicy(),
            acknowledged_dependants=dependants,
        )
        self.assertIsInstance(acknowledged, Ok)
        self.assertEqual(
            tuple(type(effect) for effect in acknowledged.value.effects), (DeleteCredential,)
        )

    def test_an_unavailable_provider_cannot_be_mutated(self) -> None:
        observation = CredentialObservation(
            _reference(), ProviderState.UNAVAILABLE, CredentialState.UNKNOWN
        )
        plan = plan_credential_mutation(
            CredentialIntent.STORE, observation, policy=EffectivePolicy()
        )
        self.assertIsInstance(plan, Err)

    def test_policy_forbids_a_provider_and_a_risk_ceiling_below_credential_mutation(self) -> None:
        observation = CredentialObservation(
            _reference(), ProviderState.AVAILABLE, CredentialState.ABSENT
        )
        forbidden = plan_credential_mutation(
            CredentialIntent.STORE,
            observation,
            (),
            policy=EffectivePolicy(allowed_credential_providers=frozenset({"enterprise-vault"})),
        )
        self.assertIsInstance(forbidden, Err)
        self.assertEqual(forbidden.diagnostics[0].code, CREDENTIAL_POLICY_VIOLATION)

        capped = plan_credential_mutation(
            CredentialIntent.STORE,
            observation,
            (),
            policy=EffectivePolicy(risk_ceiling=RiskClass.CONFIGURATION_MUTATION),
        )
        self.assertIsInstance(capped, Err)

    def test_verification_and_inspection_stay_read_only(self) -> None:
        observation = CredentialObservation(
            _reference(), ProviderState.AVAILABLE, CredentialState.PRESENT
        )
        for intent in (CredentialIntent.INSPECT, CredentialIntent.VERIFY):
            with self.subTest(intent=intent.value):
                plan = plan_credential_mutation(
                    intent,
                    observation,
                    (),
                    policy=EffectivePolicy(risk_ceiling=RiskClass.READ_ONLY),
                )
                self.assertIsInstance(plan, Ok)
                self.assertTrue(
                    all(effect.risk is RiskClass.READ_ONLY for effect in plan.value.effects)
                )

    def test_no_credential_value_exists_anywhere_in_the_domain_projection(self) -> None:
        reference_fields = {field.name for field in dataclasses.fields(CredentialReference)}
        observation_fields = {field.name for field in dataclasses.fields(CredentialObservation)}
        for forbidden in ("value", "secret", "password", "material"):
            self.assertNotIn(forbidden, reference_fields)
            self.assertNotIn(forbidden, observation_fields)
        self.assertEqual(
            credential_reference_to_data(_reference()),
            {
                "input": CREDENTIAL.value,
                "provider": {
                    "account": "agent",
                    "provider": "macos-keychain",
                    "service": "company.forge",
                },
            },
        )


class RuntimeInputPolicyPropertyTest(unittest.TestCase):
    @given(
        st.sets(st.sampled_from(("stdin", "file", "environment", "cli-argument")), min_size=1),
        st.sets(st.sampled_from(("stdin", "file", "environment", "cli-argument")), min_size=1),
        st.sets(st.sampled_from(("user-id", "forge-host")), max_size=2),
    )
    def test_restrictive_overlay_cannot_widen_input_permissions(
        self,
        parent_bindings: set[str],
        overlay_bindings: set[str],
        forbidden: set[str],
    ) -> None:
        parent = EffectivePolicy(allowed_secret_bindings=frozenset(parent_bindings))
        composed = compose_policy(
            parent,
            PolicyOverlay(
                allowed_secret_bindings=frozenset(overlay_bindings),
                forbidden_persisted_config=frozenset(forbidden),
            ),
        )

        self.assertLessEqual(composed.allowed_secret_bindings, parent.allowed_secret_bindings)
        self.assertGreaterEqual(
            composed.forbidden_persisted_config, parent.forbidden_persisted_config
        )


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
