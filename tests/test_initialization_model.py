import unittest
from datetime import datetime, timezone

from motion_server.app.initialization import (
    INITIALIZATION_CAUSE_DEFINITIONS,
    INITIALIZATION_RECOVERY_SCOPE,
    InitializationCause,
    InitializationCauseDefinition,
    InitializationFailure,
    InitializationRecoveryScope,
    InitializationStage,
    InitializationStatus,
    recovery_action_allowed,
    validate_initialization_catalog,
)


OCCURRED_AT = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)


class InitializationCatalogTest(unittest.TestCase):
    def test_every_cause_has_one_definition_with_matching_stage(self):
        self.assertEqual(
            set(INITIALIZATION_CAUSE_DEFINITIONS),
            set(InitializationCause),
        )
        for definition in INITIALIZATION_CAUSE_DEFINITIONS.values():
            self.assertIsInstance(definition, InitializationCauseDefinition)
            self.assertIsInstance(definition.stage, InitializationStage)
            self.assertTrue(definition.message)

        self.assertTrue(validate_initialization_catalog())

    def test_every_stage_has_one_minimum_recovery_scope(self):
        self.assertEqual(
            set(INITIALIZATION_RECOVERY_SCOPE),
            set(InitializationStage),
        )
        for scope in INITIALIZATION_RECOVERY_SCOPE.values():
            self.assertIsInstance(scope, InitializationRecoveryScope)

    def test_device_model_build_uses_stage_consistent_fallback_cause(self):
        definition = INITIALIZATION_CAUSE_DEFINITIONS[
            InitializationCause.DEVICE_MODEL_BUILD_FAILED
        ]

        self.assertIs(definition.stage, InitializationStage.DEVICE_MODEL_BUILD)
        self.assertNotIn("DEVICE_PROFILE_FAILED", InitializationCause.__members__)


class InitializationStatusTest(unittest.TestCase):
    def failure(self, cause=InitializationCause.BUS_CONNECTION_FAILED):
        definition = INITIALIZATION_CAUSE_DEFINITIONS[cause]
        return InitializationFailure(
            stage=definition.stage,
            cause=cause,
            message=definition.message,
            occurred_at=OCCURRED_AT,
        )

    def test_ready_status_has_no_failure(self):
        status = InitializationStatus.ready()

        self.assertTrue(status.initialized)
        self.assertIsNone(status.failure)

    def test_failed_status_requires_typed_failure(self):
        failure = self.failure()
        status = InitializationStatus.failed(failure)

        self.assertFalse(status.initialized)
        self.assertIs(status.failure, failure)

        with self.assertRaises(ValueError):
            InitializationStatus(initialized=False, failure=None)

    def test_ready_status_rejects_failure(self):
        with self.assertRaises(ValueError):
            InitializationStatus(initialized=True, failure=self.failure())

    def test_failure_rejects_stage_or_message_outside_registry_contract(self):
        with self.assertRaises(ValueError):
            InitializationFailure(
                stage=InitializationStage.RUNTIME_CREATION,
                cause=InitializationCause.BUS_CONNECTION_FAILED,
                message=(
                    INITIALIZATION_CAUSE_DEFINITIONS[
                        InitializationCause.BUS_CONNECTION_FAILED
                    ].message
                ),
                occurred_at=OCCURRED_AT,
            )

        with self.assertRaises(ValueError):
            InitializationFailure(
                stage=InitializationStage.BUS_CONNECTION,
                cause=InitializationCause.BUS_CONNECTION_FAILED,
                message="raw exception text",
                occurred_at=OCCURRED_AT,
            )


class InitializationRecoveryScopeTest(unittest.TestCase):
    def test_configuration_and_device_model_require_restart(self):
        for stage in (
            InitializationStage.CONFIGURATION,
            InitializationStage.DEVICE_MODEL_BUILD,
        ):
            self.assertFalse(
                recovery_action_allowed(
                    stage, InitializationRecoveryScope.SERVER_RESET
                )
            )
            self.assertTrue(
                recovery_action_allowed(
                    stage, InitializationRecoveryScope.SERVER_RESTART
                )
            )

    def test_runtime_creation_allows_reset_or_restart(self):
        stage = InitializationStage.RUNTIME_CREATION

        self.assertFalse(
            recovery_action_allowed(
                stage, InitializationRecoveryScope.BUS_RECONNECT
            )
        )
        self.assertTrue(
            recovery_action_allowed(stage, InitializationRecoveryScope.SERVER_RESET)
        )
        self.assertTrue(
            recovery_action_allowed(
                stage, InitializationRecoveryScope.SERVER_RESTART
            )
        )

    def test_bus_and_device_initialization_allow_all_scopes(self):
        for stage in (
            InitializationStage.BUS_CONNECTION,
            InitializationStage.DEVICE_INITIALIZATION,
        ):
            for scope in InitializationRecoveryScope:
                self.assertTrue(recovery_action_allowed(stage, scope))


if __name__ == "__main__":
    unittest.main()
