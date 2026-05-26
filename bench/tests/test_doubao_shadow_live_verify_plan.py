import contextlib
import io
import json
import unittest
from unittest.mock import patch

from bench.scripts.doubao_shadow_live_verify_plan import build_live_verify_plan, main


class DoubaoShadowLiveVerifyPlanTests(unittest.TestCase):
    def test_build_plan_describes_live_verify_without_recording_or_mutation(self):
        payload = build_live_verify_plan()

        self.assertEqual(payload["command"], "TIMEOUT=30 make doubao-shadow-live-verify")
        self.assertTrue(payload["command_requires_user_approval"])
        self.assertFalse(payload["command_mutates_state"])
        self.assertFalse(payload["command_requests_mac_permissions"])
        self.assertFalse(payload["command_records_audio"])
        self.assertEqual(payload["plan_command"], "make doubao-shadow-live-verify-plan-json")
        self.assertFalse(payload["plan_requires_user_approval"])
        self.assertFalse(payload["plan_mutates_state"])
        self.assertFalse(payload["plan_requests_mac_permissions"])
        self.assertFalse(payload["plan_records_audio"])
        self.assertTrue(payload["does_not_execute"])
        self.assertTrue(payload["waits_for_new_shadow_segment"])
        self.assertFalse(payload["records_audio"])
        self.assertEqual(payload["approval_summary"]["approval_step_count"], 1)
        self.assertEqual(payload["approval_summary"]["recording_step_indices"], [])

    def test_cli_prints_plan_json_by_default(self):
        with patch("sys.argv", ["doubao_shadow_live_verify_plan.py"]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["plan_command"], "make doubao-shadow-live-verify-plan-json")

    def test_cli_prints_human_plan(self):
        with patch("sys.argv", ["doubao_shadow_live_verify_plan.py", "--human"]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = main()

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Plan: TIMEOUT=30 make doubao-shadow-live-verify will run:", output)
        self.assertIn("This plan target does not wait for speech, run ASR, write files, request permissions, or record.", output)


if __name__ == "__main__":
    unittest.main()
