"""Run with Python 3.11.9: python -m unittest discover -s tests -v"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adb_apk_installer as app


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.adb = self.folder / "adb.exe"
        self.adb.touch()
        self.apk = self.folder / "日本語 app file.apk"
        self.apk.touch()

    def test_settings_round_trip_both_paths(self):
        config = self.folder / "config" / "settings.json"
        values = {"adb_path": str(self.adb), "apk_path": str(self.apk)}
        app.save_settings(config, values)
        self.assertEqual(app.load_settings(config), (values, ""))
        self.assertFalse(list(config.parent.glob("*.tmp")))

    def test_corrupt_settings_do_not_crash_startup(self):
        config = self.folder / "settings.json"
        for content in ("{bad", "[]"):
            config.write_text(content, encoding="utf-8")
            values, warning = app.load_settings(config)
            self.assertEqual(values, {})
            self.assertTrue(warning)

    def test_missing_settings(self):
        self.assertEqual(app.load_settings(self.folder / "absent.json"), ({}, ""))

    def test_saved_adb_has_priority_even_if_moved(self):
        with patch.object(app.shutil, "which", return_value=str(self.adb)) as which:
            self.assertEqual(app.detect_adb("C:/moved/adb.exe"), "C:/moved/adb.exe")
            which.assert_not_called()

    def test_path_detection(self):
        with patch.object(app.shutil, "which", return_value=str(self.adb)):
            self.assertEqual(app.detect_adb(), str(self.adb.resolve()))

    def test_devices_with_multiple_states_and_network_serial(self):
        output = '''* daemon started successfully *
List of devices attached
USB123 device product:foo model:Xperia_1 device:bar transport_id:1
USB456 unauthorized transport_id:2
192.168.1.2:5555 offline transport_id:3
USB789 no permissions (user in plugdev group)
'''
        devices = app.parse_devices(output)
        self.assertEqual(len(devices), 4)
        self.assertEqual(devices[0], app.Device("USB123", "device", "Xperia_1", "foo"))
        self.assertEqual(devices[1].state, "unauthorized")
        self.assertEqual(devices[2].serial, "192.168.1.2:5555")
        self.assertEqual(devices[3].state, "no permissions")
        self.assertEqual(app.parse_devices("List of devices attached\n\n"), [])

    def test_model_lookup_preserves_spaces_and_skips_unauthorized(self):
        with patch.object(app, "run_adb", side_effect=[
            "List of devices attached\nA device model:Fallback\nB unauthorized\n", "Xperia Model Test\n"
        ]) as run:
            output, devices, warnings = app.read_devices(str(self.adb))
            self.assertEqual(devices[0].model, "Xperia Model Test")
            self.assertEqual(warnings, [])
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[1], ["-s", "A", "shell", "getprop", "ro.product.model"])

    def test_model_lookup_failure_retains_devices(self):
        with patch.object(app, "run_adb", side_effect=[
            "List of devices attached\nA device model:Fallback\n", app.AdbError("offline")
        ]):
            output, devices, warnings = app.read_devices(str(self.adb))
            self.assertEqual(devices[0].model, "Fallback")
            self.assertEqual(len(warnings), 1)

    def test_install_preserves_target_and_space_unicode_path(self):
        with patch.object(app, "run_adb", side_effect=["device", "Performing Streamed Install\nSuccess"]) as run:
            output = app.install_apk(str(self.adb), "SERIAL_B", str(self.apk))
            self.assertIn("Success", output)
            self.assertEqual(run.call_args_list[0].args[1], ["-s", "SERIAL_B", "get-state"])
            self.assertEqual(run.call_args_list[1].args[1], ["-s", "SERIAL_B", "install", "-r", str(self.apk.resolve())])

    def test_unavailable_device_never_installs(self):
        with patch.object(app, "run_adb", return_value="offline") as run:
            with self.assertRaises(app.AdbError):
                app.install_apk(str(self.adb), "SERIAL_B", str(self.apk))
            self.assertEqual(run.call_count, 1)

    def test_install_failure_without_success(self):
        with patch.object(app, "run_adb", side_effect=["device", "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]"]):
            with self.assertRaisesRegex(app.AdbError, "UPDATE_INCOMPATIBLE"):
                app.install_apk(str(self.adb), "SERIAL_B", str(self.apk))

    def test_invalid_apk_and_empty_serial(self):
        with patch.object(app, "run_adb") as run:
            for serial, path in (("B", "missing.apk"), ("", str(self.apk)), ("B", str(self.adb))):
                with self.assertRaises(app.AdbError):
                    app.install_apk(str(self.adb), serial, path)
            run.assert_not_called()

    def test_subprocess_uses_argument_list_no_shell(self):
        result = subprocess.CompletedProcess([], 0, "Success\n", "")
        with patch.object(app.subprocess, "run", return_value=result) as run:
            self.assertEqual(app.run_adb(str(self.adb), ["devices", "-l"]), "Success")
            self.assertEqual(run.call_args.args[0], [str(self.adb), "devices", "-l"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_adb_error_keeps_diagnostic(self):
        result = subprocess.CompletedProcess([], 1, "", "device unauthorized")
        with patch.object(app.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(app.AdbError, "unauthorized"):
                app.run_adb(str(self.adb), ["devices"])

    def test_timeout_explains_possible_continuation(self):
        with patch.object(app.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 300)):
            with self.assertRaisesRegex(app.AdbError, "継続"):
                app.run_adb(str(self.adb), ["install", "-r", str(self.apk)], timeout=300)

    def test_missing_adb(self):
        with self.assertRaisesRegex(app.AdbError, "見つかりません"):
            app.run_adb("", ["version"])


if __name__ == "__main__":
    unittest.main()
