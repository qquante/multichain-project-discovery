"""Message formatting only: no Telegram client or external requests."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "rl-agent/rl-agent/project-agent/services/telegram/formatter.py"
spec = importlib.util.spec_from_file_location("review_formatter", PATH)
formatter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formatter)


class FormatterRegressionTests(unittest.TestCase):
    def test_enrichment_metrics_are_available_before_rendering(self):
        text, buttons = formatter.format_project_confirmed({
            "twitter_handle": "fixture_project",
            "found_in_alphagate": True,
            "avg_hunter_winrate": 72.5,
            "hunters_with_60plus_wr": 3,
            "ca_count": 2,
        })
        self.assertIn("Avg WR: 72.5%", text)
        self.assertIn("60%+ WR: 3", text)
        self.assertIn("CAs: 2", text)
        self.assertIsInstance(buttons, list)

    def test_missing_enrichment_uses_the_plain_message(self):
        text, _ = formatter.format_project_confirmed({"twitter_handle": "fixture_project"})
        self.assertNotIn("Avg WR:", text)


if __name__ == "__main__":
    unittest.main()
