import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from yt2mp3_core import sanitize_filename, validate_quality, validate_url


class SanitizeTests(unittest.TestCase):
    def test_traversal(self):
        for bad in ("..", ".", "../../x", "a/b\c", " . "):
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


if __name__ == "__main__":
    unittest.main()
