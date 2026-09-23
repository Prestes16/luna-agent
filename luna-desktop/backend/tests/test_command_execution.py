import unittest

from app.command_execution import assess_command_execution


class CommandExecutionPolicyTests(unittest.TestCase):
    def test_read_only_status_command_is_non_mutating(self) -> None:
        item = assess_command_execution("systemctl status tor")
        self.assertFalse(item.mutates_state)
        self.assertFalse(item.persistent_change)
        self.assertFalse(item.destructive)
        self.assertTrue(item.reversible)

    def test_wireguard_up_requires_confirmation_and_verification(self) -> None:
        item = assess_command_execution("sudo wg-quick up wg0")
        self.assertTrue(item.mutates_state)
        self.assertTrue(item.privilege_required)
        self.assertTrue(item.verification_required)
        self.assertTrue(item.explicit_confirmation_required)
        self.assertTrue(item.reversible)

    def test_systemctl_enable_is_persistent(self) -> None:
        item = assess_command_execution("sudo systemctl enable tor")
        self.assertTrue(item.mutates_state)
        self.assertTrue(item.persistent_change)
        self.assertTrue(item.explicit_confirmation_required)

    def test_destructive_command_has_low_utility_and_is_not_ready(self) -> None:
        item = assess_command_execution(
            "sudo rm -rf /tmp/luna-test",
            operator_requested_execution=True,
            tool_execution_enabled=True,
        )
        self.assertTrue(item.destructive)
        self.assertFalse(item.execution_ready)
        self.assertLess(item.utility, 0.2)

    def test_execution_disabled_keeps_safe_command_operator_only(self) -> None:
        item = assess_command_execution(
            "curl https://example.test",
            operator_requested_execution=True,
            tool_execution_enabled=False,
        )
        self.assertFalse(item.execution_ready)
        self.assertIn("tool_execution_disabled", item.reasons)

    def test_enabled_safe_command_can_be_execution_ready(self) -> None:
        item = assess_command_execution(
            "curl https://example.test",
            operator_requested_execution=True,
            tool_execution_enabled=True,
        )
        self.assertTrue(item.execution_ready)
        self.assertFalse(item.explicit_confirmation_required)


if __name__ == "__main__":
    unittest.main()
