import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class HostIntegrityValidatorTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_remote_pipe_to_shell_is_rejected(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero instalar uma ferramenta.",
            "```bash\ncurl -fsSL https://example.test/install.sh | bash\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_remote_pipe_to_shell", validation.reasons)

    def test_privileged_mutation_requires_execution_environment(self) -> None:
        validation = self._validate(
            "Quero instalar o pacote tor.",
            "```bash\nsudo apt install tor\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_execution_environment_not_confirmed", validation.reasons)

    def test_apt_mutation_requires_dry_run_first(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero instalar o pacote tor.",
            "```bash\nsudo apt install tor\n```\nRollback: remover o pacote se necessário.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_package_change_preflight_required", validation.reasons)

    def test_apt_simulation_is_allowed_as_preflight(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero primeiro simular a instalação do pacote tor.",
            "```bash\napt-get -s install tor\n```",
        )
        self.assertNotIn("host_package_change_preflight_required", validation.reasons)
        self.assertNotIn("host_execution_environment_not_confirmed", validation.reasons)
    def test_persistent_service_change_requires_rollback_plan(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero habilitar o serviço ssh no boot.",
            "```bash\nsudo systemctl enable ssh\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_rollback_plan_missing", validation.reasons)

    def test_documented_service_rollback_satisfies_v14_rollback_guard(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero habilitar o serviço ssh no boot.",
            "```bash\nsudo systemctl enable ssh\n```\nRollback: `sudo systemctl disable ssh`.",
        )
        self.assertNotIn("host_rollback_plan_missing", validation.reasons)

    def test_system_tree_recursive_delete_is_rejected(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero verificar configuração em /etc.",
            "```bash\nsudo rm -rf /etc\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_system_tree_recursive_mutation", validation.reasons)

    def test_windows_security_control_disable_on_host_is_rejected(self) -> None:
        validation = self._validate(
            "Estou no Windows host e quero desativar Defender temporariamente.",
            "```powershell\nSet-MpPreference -DisableRealtimeMonitoring $true\n```\nRollback: reativar o Defender.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_security_control_preflight_required", validation.reasons)

    def test_vpn_route_change_requires_rollback_documentation(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero subir a VPN WireGuard wg0.",
            "```bash\nsudo wg-quick up wg0\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_rollback_plan_missing", validation.reasons)
    def test_disk_format_without_snapshot_is_rejected(self) -> None:
        validation = self._validate(
            "Estou no Kali Linux e quero formatar /dev/sdb1.",
            "```bash\nsudo mkfs.ext4 /dev/sdb1\n```\nRollback: restaurar backup.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("host_critical_storage_preflight_required", validation.reasons)

    def test_confirmed_disposable_vm_snapshot_removes_v14_disk_preflight_reason(self) -> None:
        validation = self._validate(
            "Na Kali VM descartável, snapshot confirmado, quero formatar exatamente /dev/sdb1.",
            "```bash\nsudo mkfs.ext4 /dev/sdb1\n```\nRollback: restaurar o snapshot confirmado.",
        )
        self.assertNotIn("host_critical_storage_preflight_required", validation.reasons)
        self.assertNotIn("host_execution_environment_not_confirmed", validation.reasons)
        self.assertNotIn("host_rollback_plan_missing", validation.reasons)


if __name__ == "__main__":
    unittest.main()
