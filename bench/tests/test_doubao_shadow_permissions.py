import unittest
from pathlib import Path

from bench.scripts.doubao_shadow_permissions import (
    expected_input_device_payload,
    mac_permission_detail,
    mac_permission_payload,
    permission_guidance_for_binary,
    permission_hint_for_blockers,
    permission_targets_for_binary,
)


class DoubaoShadowPermissionTests(unittest.TestCase):
    def test_packaged_permission_targets_name_bundle_and_hosts(self):
        targets = permission_targets_for_binary(
            Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow")
        )

        self.assertEqual(
            targets,
            [
                "SwitchType.app",
                "SwitchTypeDoctor",
                "SwitchTypeDoubaoShadow",
                "Codex",
                "Terminal",
                "iTerm",
                "Cursor",
            ],
        )

    def test_debug_permission_targets_name_host_processes(self):
        targets = permission_targets_for_binary(Path("app/SwitchType/.build/debug/SwitchTypeDoubaoShadow"))

        self.assertEqual(
            targets,
            [
                "Codex",
                "Terminal",
                "iTerm",
                "Cursor",
                "SwitchTypeDoctor",
                "SwitchTypeDoubaoShadow",
            ],
        )

    def test_permission_guidance_never_points_at_doubaoime(self):
        packaged = permission_guidance_for_binary(
            Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow")
        )
        debug = permission_guidance_for_binary(Path("app/SwitchType/.build/debug/SwitchTypeDoubaoShadow"))

        self.assertIn("not DoubaoIme", packaged)
        self.assertIn("SwitchType.app", packaged)
        self.assertIn("make app-permissions", packaged)
        self.assertIn("not DoubaoIme", debug)
        self.assertIn("Codex", debug)
        self.assertIn("make app-permissions", debug)

    def test_permission_hint_only_populates_when_permissions_are_blocked(self):
        no_permission_blocker = permission_hint_for_blockers(
            ["Expected input device: unavailable"],
            Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
        )
        permission_blocker = permission_hint_for_blockers(
            ["Microphone permission: denied"],
            Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            include_refresh_recovery=True,
        )

        self.assertEqual(no_permission_blocker, {"permission_guidance": "", "permission_targets": []})
        self.assertIn("SwitchType.app", permission_blocker["permission_guidance"])
        self.assertIn("make doubao-shadow-refresh-packaged", permission_blocker["permission_guidance"])
        self.assertEqual(permission_blocker["permission_targets"][0], "SwitchType.app")

    def test_expected_input_device_payload_names_status_current_and_expected(self):
        payload = expected_input_device_payload(
            {
                "expected_input_device_status": "mismatch",
                "input_device_name": "MacBook Pro Microphone",
                "expected_input_device_name": "DJI MIC MINI",
            }
        )
        not_enforced = expected_input_device_payload(
            {
                "expected_input_device_status": "not_enforced",
                "input_device_name": None,
                "expected_input_device_name": None,
            }
        )

        self.assertEqual(
            payload,
            {
                "status": "mismatch",
                "current": "MacBook Pro Microphone",
                "expected": "DJI MIC MINI",
            },
        )
        self.assertEqual(
            not_enforced,
            {
                "status": "not_enforced",
                "current": "unavailable",
                "expected": "not enforced",
            },
        )

    def test_mac_permission_payload_names_microphone_and_accessibility(self):
        payload = mac_permission_payload(
            {
                "microphone": "denied",
                "accessibility": "granted",
            }
        )
        missing = mac_permission_payload({})

        self.assertEqual(
            payload,
            {
                "microphone": "denied",
                "accessibility": "granted",
                "all_required_granted": False,
            },
        )
        self.assertEqual(
            missing,
            {
                "microphone": "unknown",
                "accessibility": "unknown",
                "all_required_granted": False,
            },
        )

    def test_mac_permission_detail_is_compact_for_human_status(self):
        detail = mac_permission_detail(
            {
                "microphone": "denied",
                "accessibility": "granted",
                "all_required_granted": False,
            }
        )

        self.assertEqual(
            detail,
            "microphone=denied, accessibility=granted, all_required_granted=no",
        )


if __name__ == "__main__":
    unittest.main()
