import json
import subprocess
import sys
import unittest
from pathlib import Path

from bench.scripts.doubao_shadow_refresh_plan import build_refresh_plan


class DoubaoShadowRefreshPlanTests(unittest.TestCase):
    def test_refresh_plan_json_marks_preview_safe_and_steps_by_approval_need(self):
        payload = build_refresh_plan()

        self.assertEqual(payload["command"], "make doubao-shadow-refresh-packaged")
        self.assertTrue(payload["command_is_executable"])
        self.assertTrue(payload["command_requires_user_approval"])
        self.assertTrue(payload["command_mutates_state"])
        self.assertTrue(payload["command_requests_mac_permissions"])
        self.assertFalse(payload["command_records_audio"])
        self.assertEqual(payload["plan_command"], "make doubao-shadow-refresh-packaged-plan-json")
        self.assertTrue(payload["plan_is_executable"])
        self.assertFalse(payload["plan_requires_user_approval"])
        self.assertFalse(payload["plan_mutates_state"])
        self.assertFalse(payload["plan_requests_mac_permissions"])
        self.assertFalse(payload["plan_records_audio"])
        self.assertTrue(payload["does_not_execute"])
        self.assertFalse(payload["records_audio"])
        self.assertIn("not DoubaoIme", payload["permission_guidance"])
        self.assertEqual(payload["primary_permission_target"], "SwitchType.app")
        self.assertEqual(payload["permission_targets"][0], "SwitchType.app")
        self.assertEqual(
            payload["approval_summary"],
            {
                "requires_user_approval": True,
                "approval_step_count": 3,
                "steps_requiring_user_approval": [
                    {
                        "index": 1,
                        "command": "make doubao-shadow-stop",
                        "approval_reason": "stops the background recorder daemon",
                    },
                    {
                        "index": 2,
                        "command": "make package",
                        "approval_reason": "rebuilds the packaged app bundle",
                    },
                    {
                        "index": 3,
                        "command": "make app-request-permissions-packaged",
                        "approval_reason": "requests macOS Microphone/Accessibility permission prompts",
                    },
                ],
                "mutating_step_indices": [1, 2, 3],
                "permission_prompt_step_indices": [3],
                "recording_step_indices": [],
            },
        )
        self.assertEqual(
            [
                (
                    step["index"],
                    step["command"],
                    step["requires_user_approval"],
                    step["mutates_state"],
                    step["requests_mac_permissions"],
                    step["records_audio"],
                    step["approval_reason"],
                )
                for step in payload["steps"]
            ],
            [
                (
                    1,
                    "make doubao-shadow-stop",
                    True,
                    True,
                    False,
                    False,
                    "stops the background recorder daemon",
                ),
                (
                    2,
                    "make package",
                    True,
                    True,
                    False,
                    False,
                    "rebuilds the packaged app bundle",
                ),
                (
                    3,
                    "make app-request-permissions-packaged",
                    True,
                    True,
                    True,
                    False,
                    "requests macOS Microphone/Accessibility permission prompts",
                ),
                (
                    4,
                    "make doubao-shadow-preflight-packaged",
                    False,
                    False,
                    False,
                    False,
                    "read-only packaged readiness check",
                ),
            ],
        )
        self.assertTrue(all(step["is_executable_command"] for step in payload["steps"]))

    def test_cli_prints_refresh_plan_json_without_running_steps(self):
        completed = subprocess.run(
            [sys.executable, "bench/scripts/doubao_shadow_refresh_plan.py"],
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "bench"},
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["does_not_execute"])
        self.assertFalse(payload["plan_mutates_state"])
        self.assertFalse(payload["plan_requests_mac_permissions"])
        self.assertFalse(payload["plan_records_audio"])
        self.assertTrue(payload["command_mutates_state"])
        self.assertTrue(payload["command_requests_mac_permissions"])
        self.assertFalse(payload["command_records_audio"])
        self.assertFalse(payload["records_audio"])
        self.assertEqual(payload["primary_permission_target"], "SwitchType.app")
        self.assertIn("permission_targets", payload)
        self.assertIn("approval_summary", payload)
        self.assertEqual(payload["approval_summary"]["permission_prompt_step_indices"], [3])
        self.assertEqual(payload["steps"][0]["command"], "make doubao-shadow-stop")
        self.assertEqual(
            payload["steps"][2]["approval_reason"],
            "requests macOS Microphone/Accessibility permission prompts",
        )

    def test_cli_prints_human_refresh_plan_with_approval_and_safety_details(self):
        completed = subprocess.run(
            [sys.executable, "bench/scripts/doubao_shadow_refresh_plan.py", "--human"],
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "bench"},
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = completed.stdout
        self.assertIn("Plan: make doubao-shadow-refresh-packaged will run:", output)
        self.assertIn(
            "Plan command safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
            output,
        )
        self.assertIn("Target command approval: user approval required before running.", output)
        self.assertIn(
            "Target command safety: mutates_state=yes, requests_mac_permissions=yes, records_audio=no",
            output,
        )
        self.assertIn("Primary permission target: SwitchType.app", output)
        self.assertIn(
            "Approval summary: approval_steps=3, "
            "mutating_steps=1,2,3, permission_prompt_steps=3, recording_steps=none",
            output,
        )
        self.assertIn("1. make doubao-shadow-stop", output)
        self.assertIn("   approval_reason: stops the background recorder daemon", output)
        self.assertIn(
            "3. make app-request-permissions-packaged",
            output,
        )
        self.assertIn(
            "   safety: mutates_state=yes, requests_mac_permissions=yes, records_audio=no",
            output,
        )
        self.assertIn("This plan target does not stop, rebuild, request permissions, or record.", output)

    def test_makefile_and_docs_expose_refresh_plan_json(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")
        bench_readme = Path("bench/README.md").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-refresh-packaged-plan:", makefile)
        self.assertIn("bench/scripts/doubao_shadow_refresh_plan.py --human", makefile)
        self.assertIn("doubao-shadow-refresh-packaged-plan-json", makefile)
        self.assertIn("bench/scripts/doubao_shadow_refresh_plan.py", makefile)
        self.assertIn("make doubao-shadow-refresh-packaged-plan-json", readme)
        self.assertIn("permission_targets", readme)
        self.assertIn("primary_permission_target", readme)
        self.assertIn("command_mutates_state", readme)
        self.assertIn("command_requests_mac_permissions", readme)
        self.assertIn("command_records_audio", readme)
        self.assertIn("plan_mutates_state", readme)
        self.assertIn("plan_requests_mac_permissions", readme)
        self.assertIn("plan_records_audio", readme)
        self.assertIn("records_audio", readme)
        self.assertIn("approval_reason", readme)
        self.assertIn("approval_summary", readme)
        self.assertIn("approval_steps", readme)
        self.assertIn("permission_prompt_steps", readme)
        self.assertIn("make doubao-shadow-refresh-packaged-plan-json", bench_readme)
        self.assertIn("permission_targets", bench_readme)
        self.assertIn("primary_permission_target", bench_readme)
        self.assertIn("command_mutates_state", bench_readme)
        self.assertIn("command_requests_mac_permissions", bench_readme)
        self.assertIn("command_records_audio", bench_readme)
        self.assertIn("plan_mutates_state", bench_readme)
        self.assertIn("plan_requests_mac_permissions", bench_readme)
        self.assertIn("plan_records_audio", bench_readme)
        self.assertIn("records_audio", bench_readme)
        self.assertIn("approval_reason", bench_readme)
        self.assertIn("approval_summary", bench_readme)
        self.assertIn("approval_steps", bench_readme)
        self.assertIn("permission_prompt_steps", bench_readme)


if __name__ == "__main__":
    unittest.main()
