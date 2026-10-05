import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from yt2mp3_core import (build_opts, escape_template, sanitize_filename,
                         validate_quality, validate_range, validate_url)


class SanitizeTests(unittest.TestCase):
    def test_traversal(self):
        for bad in ("..", ".", "../../x", r"a/b\c", " . "):
            out = sanitize_filename(bad)
            self.assertNotIn("/", out)
            self.assertNotIn("\\", out)
            self.assertNotIn(out, ("", ".", ".."))

    def test_reserved_and_controls(self):
        self.assertNotEqual(sanitize_filename("con").upper(), "CON")
        self.assertNotIn("\n", sanitize_filename("a\nb"))
        self.assertLessEqual(len(sanitize_filename("x" * 500)), 120)

    def test_normal(self):
        self.assertEqual(sanitize_filename("My Mix 2024"), "My Mix 2024")


class ValidationTests(unittest.TestCase):
    def test_url(self):
        validate_url("https://www.youtube.com/watch?v=abc")
        for bad in ("file:///etc/passwd", "javascript:1", "", "youtube.com"):
            with self.assertRaises(ValueError):
                validate_url(bad)

    def test_quality(self):
        self.assertEqual(validate_quality("192"), "192")
        for bad in ("abc", "999", "128 -af x", ""):
            with self.assertRaises(ValueError):
                validate_quality(bad)


    def test_range(self):
        validate_range(None, None, None)
        validate_range(2, 5, 3)
        for bad in ((0, None, None), (None, -1, None), (None, None, 0),
                    (5, 2, None), ("1", None, None)):
            with self.assertRaises(ValueError):
                validate_range(*bad)


class TemplateTests(unittest.TestCase):
    def test_percent_escaped(self):
        self.assertEqual(escape_template("50% %(id)s"), "50%% %%(id)s")
        opts = build_opts(Path("C:/Music/100%"), "192", Path("a.txt"), None, None,
                          None, None, None, is_playlist=False)
        self.assertTrue(opts["outtmpl"]["default"].startswith("C:"))
        self.assertIn("100%%/", opts["outtmpl"]["default"].replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
