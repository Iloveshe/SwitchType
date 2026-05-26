import contextlib
import io
import json
import unittest
from unittest.mock import patch

from bench.scripts.doubao_shadow_capture_once_plan import build_capture_once_plan, main


class DoubaoShadowCaptureOncePlanTests(unittest.TestCase):
    def test_build_plan_describes_fixed_duration_capture_without_running_it(self):
        payload = build_capture_once_plan()

        self.assertEqual(payload["command"], "DURATION=5 make doubao-shadow-capture-once-packaged")
        self.assertTrue(payload["command_requires_user_approval"])
        self.assertTrue(payload["command_mutates_state"])
        self.assertTrue(payload["command_records_audio"])
        self.assertFalse(payload["command_requests_mac_permissions"])
        self.assertEqual(payload["plan_command"], "make doubao-shadow-capture-once-packaged-plan-json")
        self.assertFalse(payload["plan_requires_user_approval"])
        self.assertFalse(payload["plan_mutates_state"])
        self.assertFalse(payload["plan_records_audio"])
        self.assertTrue(payload["does_not_execute"])
        self.assertFalse(payload["records_audio"])
        self.assertEqual(payload["approval_summary"]["approval_step_count"], 1)
        self.assertEqual(payload["approval_summary"]["recording_step_indices"], [2])
        self.assertEqual(payload["approval_summary"]["mutating_step_indices"], [2, 3])

    def test_cli_prints_plan_json_by_default(self):
        with patch("sys.argv", ["doubao_shadow_capture_once_plan.py"]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["plan_command"], "make doubao-shadow-capture-once-packaged-plan-json")

    def test_cli_prints_human_plan(self):
        with patch("sys.argv", ["doubao_shadow_capture_once_plan.py", "--human"]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = main()

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Plan: DURATION=5 make doubao-shadow-capture-once-packaged will run:", output)
        self.assertIn("This plan target does not record, write files, run ASR, request permissions, or start capture.", output)


if __name__ == "__main__":
    unittest.main()
