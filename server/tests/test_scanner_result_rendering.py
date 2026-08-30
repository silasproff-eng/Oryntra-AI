"""Regression coverage for scanner result rendering across supported layouts."""

from pathlib import Path
import unittest


APP_JS = Path(__file__).resolve().parents[1] / "frontend" / "static" / "js" / "app.js"


class ScannerResultRenderingTests(unittest.TestCase):
    def test_optional_result_widgets_are_guarded(self):
        source = APP_JS.read_text(encoding="utf-8")

        for guard in (
            "if (chEl) {",
            "if (setupEl) {",
            "if (bannerEl) bannerEl.className",
            "if (iconEl) iconEl.textContent = sm.icon;",
            "if (labelEl) labelEl.textContent = sm.label;",
            "if (dirEl) {",
            "if (sigEl) {",
        ):
            self.assertIn(guard, source)


if __name__ == "__main__":
    unittest.main()
