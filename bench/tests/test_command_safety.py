import unittest

from bench.scripts.command_safety import (
    command_is_executable,
    command_mutates_state,
    command_records_audio,
    command_requests_mac_permissions,
    command_requires_user_approval,
    format_command_approval,
    format_command_safety,
)


class CommandSafetyTests(unittest.TestCase):
    def test_identifies_make_commands_with_environment_prefixes_as_executable(self):
        self.assertTrue(command_is_executable("make doubao-shadow-status"))
        self.assertTrue(command_is_executable("TIMEOUT=30 make doubao-shadow-live-verify"))
        self.assertTrue(command_is_executable("DURATION=5 PRE_DELAY=2 make doubao-shadow-capture-once-packaged"))
        self.assertTrue(
            command_is_executable(
                'SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" make doubao-shadow-status'
            )
        )

    def test_rejects_commands_with_shell_control_syntax(self):
        self.assertFalse(command_is_executable("FOO=1; make doubao-shadow-status"))
        self.assertFalse(command_is_executable("make doubao-shadow-status && make doubao-shadow-start"))
        self.assertFalse(command_is_executable("make doubao-shadow-status | tee status.json"))

    def test_rejects_malformed_quoted_commands(self):
        self.assertFalse(command_is_executable('FOO="unterminated make doubao-shadow-status'))

    def test_human_guidance_is_not_an_executable_command(self):
        guidance = "use Doubao voice input now; if you already tried, run make hotkey-probe"

        self.assertFalse(command_is_executable(guidance))
        self.assertFalse(command_requires_user_approval(guidance))

    def test_refresh_plan_targets_are_executable_but_do_not_require_approval(self):
        self.assertTrue(command_is_executable("make doubao-shadow-refresh-packaged-plan"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-refresh-packaged-plan"))
        self.assertTrue(command_is_executable("make doubao-shadow-refresh-packaged-plan-json"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-refresh-packaged-plan-json"))
        self.assertTrue(command_is_executable("make doubao-shadow-reconcile-current-plan"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-reconcile-current-plan"))
        self.assertFalse(command_mutates_state("make doubao-shadow-reconcile-current-plan"))
        self.assertTrue(command_is_executable("make doubao-shadow-reconcile-current-plan-json"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-reconcile-current-plan-json"))
        self.assertFalse(command_mutates_state("make doubao-shadow-reconcile-current-plan-json"))
        self.assertTrue(command_is_executable("make doubao-shadow-live-verify-plan"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-live-verify-plan"))
        self.assertFalse(command_mutates_state("make doubao-shadow-live-verify-plan"))
        self.assertFalse(command_records_audio("make doubao-shadow-live-verify-plan"))
        self.assertTrue(command_is_executable("make doubao-shadow-live-verify-plan-json"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-live-verify-plan-json"))
        self.assertFalse(command_mutates_state("make doubao-shadow-live-verify-plan-json"))
        self.assertFalse(command_records_audio("make doubao-shadow-live-verify-plan-json"))
        self.assertTrue(command_is_executable("make doubao-shadow-capture-once-packaged-plan"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-capture-once-packaged-plan"))
        self.assertFalse(command_mutates_state("make doubao-shadow-capture-once-packaged-plan"))
        self.assertFalse(command_records_audio("make doubao-shadow-capture-once-packaged-plan"))
        self.assertTrue(command_is_executable("make doubao-shadow-capture-once-packaged-plan-json"))
        self.assertFalse(command_requires_user_approval("make doubao-shadow-capture-once-packaged-plan-json"))
        self.assertFalse(command_mutates_state("make doubao-shadow-capture-once-packaged-plan-json"))
        self.assertFalse(command_records_audio("make doubao-shadow-capture-once-packaged-plan-json"))
        self.assertTrue(command_is_executable("make hotkey-probe-packaged-plan"))
        self.assertFalse(command_requires_user_approval("make hotkey-probe-packaged-plan"))
        self.assertFalse(command_mutates_state("make hotkey-probe-packaged-plan"))
        self.assertFalse(command_records_audio("make hotkey-probe-packaged-plan"))
        self.assertTrue(command_is_executable("make hotkey-probe-packaged-plan-json"))
        self.assertFalse(command_requires_user_approval("make hotkey-probe-packaged-plan-json"))
        self.assertFalse(command_mutates_state("make hotkey-probe-packaged-plan-json"))
        self.assertFalse(command_records_audio("make hotkey-probe-packaged-plan-json"))

    def test_state_mutating_shadow_stop_requires_approval(self):
        self.assertTrue(command_is_executable("make doubao-shadow-stop"))
        self.assertTrue(command_requires_user_approval("make doubao-shadow-stop"))

    def test_records_audio_only_for_commands_that_turn_on_recording(self):
        self.assertTrue(command_records_audio("make doubao-shadow-start-auto"))
        self.assertTrue(command_records_audio("make doubao-shadow-start-auto-packaged"))
        self.assertTrue(command_records_audio("make doubao-shadow-record"))
        self.assertTrue(command_records_audio("DURATION=5 make doubao-shadow-capture-once-packaged"))
        self.assertTrue(command_records_audio("make doubao-shadow-restart-packaged"))
        self.assertFalse(command_records_audio("make doubao-shadow-refresh-packaged"))
        self.assertFalse(command_records_audio("make doubao-shadow-refresh-packaged-plan-json"))
        self.assertFalse(command_records_audio("make doubao-shadow-stop"))
        self.assertFalse(command_records_audio("make doubao-shadow-status"))
        self.assertFalse(command_records_audio("make doubao-shadow-live-verify"))
        self.assertFalse(command_records_audio("check SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"))

    def test_mutates_state_for_process_build_permission_and_capture_commands(self):
        self.assertTrue(command_mutates_state("make doubao-shadow-start-auto"))
        self.assertTrue(command_mutates_state("make doubao-shadow-stop"))
        self.assertTrue(command_mutates_state("make doubao-shadow-refresh-packaged"))
        self.assertTrue(command_mutates_state("make doubao-shadow-reconcile-current"))
        self.assertTrue(command_mutates_state("make doubao-shadow-reconcile-auto"))
        self.assertTrue(command_mutates_state("make doubao-shadow-import-review"))
        self.assertTrue(command_mutates_state("make doubao-shadow-review-sheet"))
        self.assertTrue(command_mutates_state("make package"))
        self.assertTrue(command_mutates_state("make swift-build"))
        self.assertTrue(command_mutates_state("make app-request-permissions-packaged"))
        self.assertTrue(command_mutates_state("DURATION=5 make doubao-shadow-capture-once-packaged"))
        self.assertFalse(command_mutates_state("make doubao-shadow-refresh-packaged-plan-json"))
        self.assertFalse(command_mutates_state("make doubao-shadow-preflight-packaged"))
        self.assertFalse(command_mutates_state("make doubao-shadow-status"))
        self.assertFalse(command_mutates_state("make doubao-shadow-live-verify"))
        self.assertFalse(command_mutates_state("check SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"))

    def test_reconcile_commands_require_approval_but_do_not_record_or_request_permissions(self):
        for command in [
            "make doubao-shadow-reconcile",
            "make doubao-shadow-reconcile-current",
            "make doubao-shadow-reconcile-auto",
            "make doubao-shadow-import-review",
            "make doubao-shadow-review-sheet",
        ]:
            with self.subTest(command=command):
                self.assertTrue(command_requires_user_approval(command))
                self.assertTrue(command_mutates_state(command))
                self.assertFalse(command_records_audio(command))
                self.assertFalse(command_requests_mac_permissions(command))

    def test_requests_mac_permissions_only_for_permission_prompt_commands(self):
        self.assertTrue(command_requests_mac_permissions("make app-permissions"))
        self.assertTrue(command_requests_mac_permissions("make app-request-permissions"))
        self.assertTrue(command_requests_mac_permissions("make app-request-permissions-packaged"))
        self.assertTrue(command_requests_mac_permissions("make doubao-shadow-refresh-packaged"))
        self.assertFalse(command_requests_mac_permissions("make package"))
        self.assertFalse(command_requests_mac_permissions("make doubao-shadow-start-auto"))
        self.assertFalse(command_requests_mac_permissions("make doubao-shadow-preflight-packaged"))
        self.assertFalse(command_requests_mac_permissions("make hotkey-probe-packaged"))
        self.assertFalse(command_requests_mac_permissions("check SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"))

    def test_formats_command_approval_for_human_output(self):
        self.assertEqual(
            format_command_approval("Next command", "make doubao-shadow-status"),
            "Next command approval: no approval needed.",
        )
        self.assertEqual(
            format_command_approval("Next command", "make doubao-shadow-refresh-packaged"),
            "Next command approval: user approval required before running.",
        )
        self.assertEqual(
            format_command_approval("Next action", "use Doubao voice input now"),
            "Next action approval: guidance, not an executable command.",
        )

    def test_formats_command_safety_for_human_output(self):
        self.assertEqual(
            format_command_safety(
                "Next command",
                mutates_state=True,
                requests_mac_permissions=False,
                records_audio=True,
            ),
            "Next command safety: mutates_state=yes, requests_mac_permissions=no, records_audio=yes",
        )
        self.assertEqual(
            format_command_safety(
                "Preview",
                mutates_state=False,
                requests_mac_permissions=False,
                records_audio=False,
            ),
            "Preview safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
        )


if __name__ == "__main__":
    unittest.main()
