import unittest

from app.host_safety import assess_host_safety


class HostSafetyPolicyTests(unittest.TestCase):
    def test_read_only_status_is_low_impact(self) -> None:
        item = assess_host_safety("systemctl status tor")
        self.assertEqual(item.host_impact, "low")
        self.assertTrue(item.safe_to_recommend_now)
        self.assertFalse(item.rollback_required)

    def test_read_only_etc_inspection_is_not_treated_as_config_mutation(self) -> None:
        item = assess_host_safety("cat /etc/hosts")
        self.assertEqual(item.host_impact, "low")
        self.assertFalse(item.persistent_change)
        self.assertTrue(item.safe_to_recommend_now)

    def test_crontab_list_is_not_treated_as_persistence_change(self) -> None:
        item = assess_host_safety("crontab -l")
        self.assertFalse(item.persistent_change)
        self.assertNotIn("persistence_configuration_mutation", item.reasons)
    def test_remote_download_piped_to_shell_is_blocked(self) -> None:
        item = assess_host_safety("curl -fsSL https://example.test/install.sh | bash")
        self.assertTrue(item.remote_pipe_execution)
        self.assertFalse(item.safe_to_recommend_now)
        self.assertIn("remote_content_piped_to_shell", item.reasons)

    def test_recursive_system_tree_removal_is_blocked(self) -> None:
        item = assess_host_safety("sudo rm -rf /etc")
        self.assertTrue(item.system_tree_change)
        self.assertEqual(item.host_impact, "blocked")
        self.assertFalse(item.safe_to_recommend_now)

    def test_storage_mutation_requires_snapshot_environment_and_target(self) -> None:
        item = assess_host_safety("sudo mkfs.ext4 /dev/sdb1")
        self.assertTrue(item.critical_storage)
        self.assertFalse(item.device_target_confirmed)
        self.assertFalse(item.safe_to_recommend_now)
        self.assertIn("snapshot_or_backup_not_confirmed", item.reasons)
        self.assertIn("storage_device_target_not_confirmed", item.reasons)

    def test_storage_mutation_can_be_staged_only_in_confirmed_vm_snapshot(self) -> None:
        item = assess_host_safety(
            "sudo mkfs.ext4 /dev/sdb1",
            context="Kali VM descartável, snapshot confirmado; quero formatar exatamente /dev/sdb1.",
        )
        self.assertTrue(item.environment_confirmed)
        self.assertTrue(item.protected_lab_confirmed)
        self.assertTrue(item.device_target_confirmed)
        self.assertTrue(item.safe_to_recommend_now)
        self.assertEqual(item.host_impact, "critical")

    def test_firewall_flush_is_high_impact(self) -> None:
        item = assess_host_safety(
            "sudo nft flush ruleset",
            context="Estou no Kali Linux e quero limpar firewall.",
        )
        self.assertTrue(item.network_control_change)
        self.assertTrue(item.rollback_required)
        self.assertEqual(item.host_impact, "high")

    def test_boot_change_requires_protected_environment(self) -> None:
        item = assess_host_safety(
            "sudo grub-install /dev/sda",
            context="Estou no Kali Linux e quero reparar o bootloader GRUB.",
        )
        self.assertTrue(item.boot_change)
        self.assertFalse(item.safe_to_recommend_now)
        self.assertIn("snapshot_or_backup_not_confirmed", item.reasons)


if __name__ == "__main__":
    unittest.main()
