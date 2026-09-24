import unittest

from app.kali_tool_dictionary import execution_baseline_for_tool


class KaliToolDictionaryTests(unittest.TestCase):
    def test_execution_baselines_are_conservative(self) -> None:
        self.assertEqual(execution_baseline_for_tool("nmap"), "L1_PROBE")
        self.assertEqual(execution_baseline_for_tool("hydra"), "L3_HIGH_IMPACT")
        self.assertEqual(execution_baseline_for_tool("openvpn"), "L2_MUTATE")
        self.assertEqual(execution_baseline_for_tool("wg"), "L0_OBSERVE")
        self.assertIsNone(execution_baseline_for_tool("not-a-real-tool"))


if __name__ == "__main__":
    unittest.main()
