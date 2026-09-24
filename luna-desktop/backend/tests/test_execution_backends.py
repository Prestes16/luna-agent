import shlex
import unittest

from app.execution_backends import (
    SSHExecutionConfig,
    build_ssh_process_argv,
    resolve_ssh_binary,
    ssh_local_file_issues,
)


class ExecutionBackendTests(unittest.TestCase):
    def test_ssh_backend_preserves_strict_host_key_policy(self) -> None:
        config = SSHExecutionConfig(
            host="192.168.56.10",
            user="kali",
            port=22,
            host_key_policy="strict",
        )
        argv = build_ssh_process_argv(
            config,
            ("nmap", "-sV", "10.10.10.5"),
        )
        self.assertEqual(argv[0], "ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("kali@192.168.56.10", argv)
        self.assertEqual(argv[-1], "nmap -sV 10.10.10.5")

    def test_ssh_remote_arguments_are_shell_quoted(self) -> None:
        config = SSHExecutionConfig(
            host="kali-vm.localdomain",
            user="analyst",
            host_key_policy="accept-new",
        )
        argv = build_ssh_process_argv(
            config,
            (
                "curl",
                "-H",
                "Authorization: Bearer TEST TOKEN",
                "https://target.test/api",
            ),
        )
        remote = argv[-1]
        self.assertIn("'Authorization: Bearer TEST TOKEN'", remote)
        self.assertEqual(
            shlex.split(remote),
            [
                "curl",
                "-H",
                "Authorization: Bearer TEST TOKEN",
                "https://target.test/api",
            ],
        )
        self.assertIn("StrictHostKeyChecking=accept-new", argv)

    def test_ssh_identity_and_known_hosts_are_explicit(self) -> None:
        config = SSHExecutionConfig(
            host="10.0.0.20",
            user="kali",
            port=2222,
            identity_file=r"D:\LunaCyber\keys\kali_ed25519",
            known_hosts_file=r"D:\LunaCyber\config\known_hosts",
        )
        argv = build_ssh_process_argv(config, ("id",))
        self.assertIn("-i", argv)
        self.assertIn(r"D:\LunaCyber\keys\kali_ed25519", argv)
        self.assertIn("UserKnownHostsFile=D:\\LunaCyber\\config\\known_hosts", argv)
        self.assertIn("2222", argv)

    def test_invalid_ssh_identity_fields_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            SSHExecutionConfig(host="bad host", user="kali").validated()
        with self.assertRaises(ValueError):
            SSHExecutionConfig(host="10.0.0.2", user="bad user").validated()
        with self.assertRaises(ValueError):
            SSHExecutionConfig(host="10.0.0.2", user="kali", port=70000).validated()
        with self.assertRaises(ValueError):
            SSHExecutionConfig(
                host="10.0.0.2",
                user="kali",
                host_key_policy="off",
            ).validated()

    def test_from_env_parses_complete_kali_contract(self) -> None:
        config = SSHExecutionConfig.from_env({
            "LUNA_KALI_SSH_HOST": "192.168.56.10",
            "LUNA_KALI_SSH_USER": "kali",
            "LUNA_KALI_SSH_PORT": "2222",
            "LUNA_KALI_SSH_IDENTITY": r"D:\\LunaCyber\\keys\\kali_ed25519",
            "LUNA_KALI_SSH_KNOWN_HOSTS": r"D:\\LunaCyber\\config\\known_hosts",
            "LUNA_KALI_SSH_HOST_KEY_POLICY": "strict",
            "LUNA_KALI_SSH_CONNECT_TIMEOUT": "15",
        })
        self.assertEqual(config.host, "192.168.56.10")
        self.assertEqual(config.user, "kali")
        self.assertEqual(config.port, 2222)
        self.assertEqual(config.connect_timeout_seconds, 15)
        self.assertEqual(config.host_key_policy, "strict")

    def test_from_env_rejects_invalid_numeric_configuration_instead_of_clamping(self) -> None:
        base = {
            "LUNA_KALI_SSH_HOST": "192.168.56.10",
            "LUNA_KALI_SSH_USER": "kali",
        }
        with self.assertRaises(ValueError):
            SSHExecutionConfig.from_env({
                **base,
                "LUNA_KALI_SSH_PORT": "not-a-port",
            })
        with self.assertRaises(ValueError):
            SSHExecutionConfig.from_env({
                **base,
                "LUNA_KALI_SSH_PORT": "70000",
            })
        with self.assertRaises(ValueError):
            SSHExecutionConfig.from_env({
                **base,
                "LUNA_KALI_SSH_CONNECT_TIMEOUT": "0",
            })

    def test_public_config_hides_local_file_paths(self) -> None:
        config = SSHExecutionConfig(
            host="10.0.0.2",
            user="kali",
            identity_file=r"D:\secret\id_ed25519",
            known_hosts_file=r"D:\secret\known_hosts",
        )
        public = config.public_dict()
        self.assertTrue(public["identity_file"])
        self.assertTrue(public["known_hosts_file"])
        self.assertNotIn(r"D:\secret\id_ed25519", str(public))


    def test_explicit_ssh_binary_is_preserved(self) -> None:
        config = SSHExecutionConfig(
            host="10.0.0.2",
            user="kali",
            ssh_binary=r"C:\\Windows\\System32\\OpenSSH\\ssh.exe",
        )
        argv = build_ssh_process_argv(config, ("id",))
        self.assertEqual(
            argv[0],
            r"C:\\Windows\\System32\\OpenSSH\\ssh.exe",
        )

    def test_configured_missing_identity_is_reported(self) -> None:
        config = SSHExecutionConfig(
            host="10.0.0.2",
            user="kali",
            identity_file=r"Z:\\definitely-missing\\id_ed25519",
        )
        self.assertIn("identity_file_not_found", ssh_local_file_issues(config))

    def test_public_config_does_not_expose_explicit_ssh_binary_path(self) -> None:
        config = SSHExecutionConfig(
            host="10.0.0.2",
            user="kali",
            ssh_binary=r"C:\\Windows\\System32\\OpenSSH\\ssh.exe",
        )
        public = config.public_dict()
        self.assertEqual(public["ssh_binary"].casefold(), "ssh.exe")
        self.assertNotIn("System32", str(public))

if __name__ == "__main__":
    unittest.main()
