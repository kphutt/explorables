"""Unit tests for the rule that every server feature explorables do not use stays off.

    python -m unittest discover -s scripts -p "test_*.py"

Each test starts from a copy of the real server config, turns one feature back on, leaves it
out or misspells it, and checks the gate names it.
"""

from __future__ import annotations

import copy
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check as ce  # noqa: E402
import rules  # noqa: E402

# A value that turns each feature back on.
ON = {
    "health": True,
    "metrics": True,
    "maintenance-mode": True,
    "accept-markdown": True,
    "cors-allow-origins": "https://example.com",
    "basic-auth": "user:$2y$05$hash",
    "page-fallback": "index.html",
    "directory-listing": True,
    "directory-listing-download": ["targz"],
    "compression-static": True,
    "follow-symlinks": True,
    "tls": True,
    "http2": True,
    "https-redirect": True,
    "use-relative-root": True,
    "etag": True,
    "log-remote-address": True,
    "log-x-real-ip": True,
    "log-forwarded-for": True,
}

NAME = "server/sws.toml"
ADVANCED = frozenset({"headers"})


class Settings(unittest.TestCase):
    def setUp(self):
        self.parsed = tomllib.loads(ce.CONFIG.read_text(encoding="utf-8"))

    def problems(self, parsed=None) -> list:
        return rules.server_settings_problems(NAME, parsed or self.parsed, ADVANCED)

    def changed(self, key, value=None, remove=False) -> list:
        parsed = copy.deepcopy(self.parsed)
        if remove:
            del parsed["general"][key]
        else:
            parsed["general"][key] = value
        return self.problems(parsed)

    def assertNames(self, problems, needle):
        self.assertTrue(any(needle in p for p in problems), f"no problem mentioning {needle!r}: {problems}")

    def test_the_real_config_passes(self):
        self.assertEqual(self.problems(), [])

    def test_every_feature_on_fails(self):
        self.assertEqual(set(ON), set(rules.SERVER_FEATURES_OFF), "ON must cover every feature the gate turns off")
        for key, value in ON.items():
            with self.subTest(key=key):
                self.assertNames(self.changed(key, value), f"{key} is {value!r}")

    def test_every_feature_left_out_fails(self):
        for key in rules.SERVER_FEATURES_OFF:
            with self.subTest(key=key):
                self.assertNames(self.changed(key, remove=True), f"{key} must be set")

    def test_off_written_with_the_wrong_type_fails(self):
        # 0 == False in Python, and SWS would reject "false" for a bool, but neither is the
        # value the gate means, so neither passes.
        self.assertNames(self.changed("health", 0), "health is 0")
        self.assertNames(self.changed("cors-allow-origins", []), "cors-allow-origins is []")

    def test_a_key_is_either_off_or_allowed(self):
        # A key in both lists reads as free to set, though the gate holds it off.
        self.assertEqual(set(rules.SERVER_FEATURES_OFF) & rules.SERVER_KEYS_ALLOWED, set())

    def test_unknown_key_fails(self):
        self.assertNames(self.changed("rewrites", True), "rewrites is not a key this gate knows")

    def test_misspelled_key_fails(self):
        # SWS would warn about helth and keep health at its default.
        parsed = copy.deepcopy(self.parsed)
        parsed["general"]["helth"] = parsed["general"].pop("health")
        problems = self.problems(parsed)
        self.assertNames(problems, "helth is not a key this gate knows")
        self.assertNames(problems, "health must be set")

    def test_v2_key_fails(self):
        self.assertNames(self.changed("ignore-hidden-files", True), "ignore-hidden-files is not a key")

    def test_unknown_section_fails(self):
        parsed = copy.deepcopy(self.parsed)
        parsed["extra"] = {}
        self.assertNames(self.problems(parsed), "[extra] is not a section")

    def test_advanced_features_fail(self):
        for table in ("rewrites", "redirects", "virtual-hosts", "memory-cache"):
            with self.subTest(table=table):
                parsed = copy.deepcopy(self.parsed)
                parsed["advanced"][table] = [{"source": "/a", "destination": "/b"}]
                self.assertNames(self.problems(parsed), f"[advanced.{table}]")

    def test_idle_timeout_zero_fails(self):
        self.assertNames(self.changed("idle-timeout", 0), "idle-timeout must be set")

    def test_idle_timeout_negative_fails(self):
        self.assertNames(self.changed("idle-timeout", -1), "idle-timeout must be set")

    def test_idle_timeout_left_out_fails(self):
        self.assertNames(self.changed("idle-timeout", remove=True), "idle-timeout must be set")

    def test_idle_timeout_not_a_number_fails(self):
        self.assertNames(self.changed("idle-timeout", True), "idle-timeout must be set")
        self.assertNames(self.changed("idle-timeout", "30"), "idle-timeout must be set")

    def test_idle_timeout_of_one_passes(self):
        self.assertEqual(self.changed("idle-timeout", 1), [])


class Wired(unittest.TestCase):
    """The gate runs the rule on the file it is given, not on parsed data."""

    def edited(self, old: str, new: str) -> list:
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "server"
            server.mkdir()
            config = server / "sws.toml"
            text = ce.CONFIG.read_text(encoding="utf-8")
            self.assertIn(old, text)
            config.write_text(text.replace(old, new, 1), encoding="utf-8")
            failures = []
            ce.check_server(failures, config)
            return failures

    def test_the_gate_passes_the_real_config(self):
        failures = []
        ce.check_server(failures)
        self.assertEqual(failures, [])

    def test_the_gate_reads_its_config(self):
        failures = self.edited("health = false", "health = true")
        self.assertTrue(any("health is True" in f for f in failures), failures)

    def test_the_gate_checks_idle_timeout(self):
        failures = self.edited("idle-timeout = 30", "idle-timeout = 0")
        self.assertTrue(any("idle-timeout must be set" in f for f in failures), failures)

    def test_the_gate_refuses_redirects(self):
        rule = '\n[[advanced.redirects]]\nsource = "/a"\ndestination = "/b"\nkind = 301\n'
        failures = self.edited("[advanced]\n", "[advanced]\n" + rule)
        self.assertTrue(any("[advanced.redirects]" in f for f in failures), failures)

    def test_a_file_it_cannot_read_fails(self):
        failures = []
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "server").mkdir()
            rules.check_server_settings(failures, Path(tmp) / "server" / "missing.toml")
        self.assertTrue(any("could not be read" in f for f in failures), failures)

    def test_the_default_allows_only_headers(self):
        rule = '\n[[advanced.redirects]]\nsource = "/a"\ndestination = "/b"\nkind = 301\n'
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "server"
            server.mkdir()
            config = server / "sws.toml"
            config.write_text(ce.CONFIG.read_text(encoding="utf-8").replace("[advanced]\n", "[advanced]\n" + rule, 1),
                              encoding="utf-8")
            failures = []
            rules.check_server_settings(failures, config)
        self.assertTrue(any("[advanced.redirects]" in f for f in failures), failures)


if __name__ == "__main__":
    unittest.main()
