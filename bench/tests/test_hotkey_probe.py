import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bench.scripts.run_hotkey_probe import binary_supports_timeout, run_hotkey_probe


class HotkeyProbeTests(unittest.TestCase):
    def test_package_exposes_hotkey_probe_executable(self):
        package = Path("app/SwitchType/Package.swift").read_text(encoding="utf-8")
        package_script = Path("scripts/package_app.sh").read_text(encoding="utf-8")

        self.assertIn('executable(name: "SwitchTypeHotkeyProbe"', package)
        self.assertIn('name: "SwitchTypeHotkeyProbe"', package)
        self.assertIn('SwitchTypeHotkeyProbe', package_script)

    def test_hotkey_probe_prints_copyable_environment(self):
        source = Path("app/SwitchType/Sources/SwitchTypeHotkeyProbe/main.swift").read_text(encoding="utf-8")

        self.assertIn("SWITCHTYPE_HOTKEY_KEY_CODE", source)
        self.assertIn("SWITCHTYPE_HOTKEY_MODIFIERS", source)
        self.assertIn(".listenOnly", source)
        self.assertIn("flagsChanged", source)
        self.assertIn("make doubao-shadow-start-auto", source)
        self.assertNotIn("isModifierKey", source)

    def test_hotkey_probe_supports_timeout_diagnostics(self):
        source = Path("app/SwitchType/Sources/SwitchTypeHotkeyProbe/main.swift").read_text(encoding="utf-8")
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("--timeout-seconds", source)
        self.assertIn("No hotkey detected", source)
        self.assertIn("TIMEOUT=$${TIMEOUT:-0}", makefile)
        self.assertIn("--timeout-seconds $$TIMEOUT", makefile)
        self.assertIn("run_hotkey_probe.py", makefile)

    def test_probe_wrapper_refuses_stale_binary_without_touching_event_tap(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "SwitchTypeHotkeyProbe"
            binary.write_bytes(b"old probe without timeout support")
            calls = []

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = run_hotkey_probe(
                    binary=binary,
                    timeout_seconds=30,
                    package_command="make package",
                    runner=lambda command: calls.append(command) or 0,
                )

        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        output = stdout.getvalue()
        self.assertIn("does not support --timeout-seconds", output)
        self.assertIn("make package", output)
        self.assertIn("make app-request-permissions-packaged", output)

    def test_probe_wrapper_runs_timeout_when_binary_supports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "SwitchTypeHotkeyProbe"
            binary.write_bytes(b"new probe --timeout-seconds support")
            calls = []

            code = run_hotkey_probe(
                binary=binary,
                timeout_seconds=30,
                package_command="make package",
                runner=lambda command: calls.append(command) or 0,
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls, [[str(binary), "--timeout-seconds", "30"]])

    def test_binary_supports_timeout_reads_marker_without_executing_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "SwitchTypeHotkeyProbe"
            binary.write_bytes(b"Usage: SwitchTypeHotkeyProbe [--timeout-seconds seconds]")

            self.assertTrue(binary_supports_timeout(binary))

    def test_makefile_exposes_hotkey_probe_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("hotkey-probe:", makefile)
        self.assertIn("hotkey-probe-packaged:", makefile)
        self.assertIn("hotkey-probe-packaged-plan:", makefile)
        self.assertIn("hotkey-probe-packaged-plan-json:", makefile)
        self.assertIn("SwitchTypeHotkeyProbe", makefile)

    def test_docs_explain_probe_before_shadow_start(self):
        readme = Path("bench/README.md").read_text(encoding="utf-8")

        self.assertIn("make hotkey-probe", readme)
        self.assertIn("make hotkey-probe-packaged", readme)
        self.assertIn("make hotkey-probe-packaged-plan-json", readme)
        self.assertIn("TIMEOUT=30 make hotkey-probe-packaged", readme)
        self.assertIn("prints `SWITCHTYPE_HOTKEY_KEY_CODE`", readme)
        self.assertIn("make doubao-shadow-start-auto", readme)


if __name__ == "__main__":
    unittest.main()
