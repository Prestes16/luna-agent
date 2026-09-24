import unittest

from app.execution_backends import (
    SSHExecutionConfig,
    build_ssh_process_argv,
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
        self.assertIn("'https://target.test/api'", remote)
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


if __name__ == "__main__":
    unittest.main()
