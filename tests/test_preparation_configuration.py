"""Offline regressions for cookie configuration in the prepared copies."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_client(path):
    spec = importlib.util.spec_from_file_location("review_cookie_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AlphaGateClient


class CookieConfigurationTests(unittest.TestCase):
    def adapters(self):
        paths = sorted(ROOT.rglob("alphagate_client.py"))
        self.assertEqual(len(paths), 2)
        return paths

    def test_no_embedded_session_when_environment_is_missing(self):
        for path in self.adapters():
            with self.subTest(path=str(path.relative_to(ROOT))):
                with patch.dict(os.environ, {}, clear=True):
                    client = load_client(path)
                    self.assertEqual(client.COOKIES["userId"], "")
                    self.assertEqual(client.COOKIES["extensionSessionId"], "")

    def test_session_is_loaded_from_explicit_environment(self):
        for path in self.adapters():
            with self.subTest(path=str(path.relative_to(ROOT))):
                with patch.dict(os.environ, {
                    "ALPHAGATE_USER_ID": "fixture-user",
                    "ALPHAGATE_SESSION_ID": "fixture-session",
                }, clear=True):
                    client = load_client(path)
                    self.assertEqual(client.COOKIES["userId"], "fixture-user")
                    self.assertEqual(client.COOKIES["extensionSessionId"], "fixture-session")


if __name__ == "__main__":
    unittest.main()
