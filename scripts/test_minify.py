"""Unit tests for scripts/minify.py and scripts/check_minify.py. Standard library only.

    python -m unittest discover -s scripts -p "test_*.py"

The CSS and HTML steps and the comparison are tested here, without npm. terser itself, and
the whole check from a clean `npm ci`, run in scripts/check_minify.py (CI and pre-push).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_minify  # noqa: E402
import minify  # noqa: E402


class Css(unittest.TestCase):
    def test_comments_and_whitespace_go(self):
        self.assertEqual(minify.css("/* a */\na  ,  b > c {\n  color: red;\n  margin: 0;\n}\n"),
                         "a,b>c{color: red;margin: 0}\n")

    def test_spaces_around_a_colon_stay(self):
        # Dropping them would turn the descendant selector `a :hover` into `a:hover`.
        self.assertEqual(minify.css("a :hover { x: 1 }"), "a :hover{x: 1}\n")

    def test_spaces_around_a_plus_stay(self):
        self.assertEqual(minify.css("a + b { x: calc(1px + 2px) }"), "a + b{x: calc(1px + 2px)}\n")


class Html(unittest.TestCase):
    def test_indents_become_one_newline(self):
        self.assertEqual(minify.html("<ul>\n    <li>a</li>\n\n\t<li>b</li>\n</ul>\n"), "<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n")

    def test_text_inside_a_line_is_kept(self):
        self.assertEqual(minify.html("<p>two  spaces</p>\n"), "<p>two  spaces</p>\n")


class Compare(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.slug = tmp / "pages" / "demo"
        (self.slug / "src").mkdir(parents=True)
        (self.slug / "src" / "style.css").write_text("a { x: 1; }\n", encoding="utf-8")
        (self.slug / "src" / "index.html").write_text("<p>\n  hi\n</p>\n", encoding="utf-8")
        (self.slug / "src" / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
        self.built = tmp / "out"
        self.written = minify.minify(self.slug / "src", self.built, tmp / "node_modules")
        for rel in self.written:
            (self.slug / rel).write_bytes((self.built / rel).read_bytes())

    def tearDown(self):
        self._tmp.cleanup()

    def test_matching_files_pass(self):
        self.assertEqual(check_minify.compare(self.slug, self.built, self.written), [])

    def test_other_files_are_copied_as_they_are(self):
        self.assertEqual((self.built / "icon.svg").read_text(encoding="utf-8"), "<svg/>\n")

    def test_a_served_file_edited_by_hand(self):
        (self.slug / "style.css").write_text("a{x: 2}\n", encoding="utf-8")
        problems = check_minify.compare(self.slug, self.built, self.written)
        self.assertTrue(any("pages/demo/style.css: sha256" in p for p in problems), problems)

    def test_a_line_ending_change_fails(self):
        (self.slug / "index.html").write_bytes((self.slug / "index.html").read_bytes().replace(b"\n", b"\r\n"))
        self.assertTrue(check_minify.compare(self.slug, self.built, self.written))

    def test_a_served_file_missing(self):
        (self.slug / "style.css").unlink()
        problems = check_minify.compare(self.slug, self.built, self.written)
        self.assertTrue(any("missing" in p for p in problems), problems)

    def test_only_explorables_with_sources_are_checked(self):
        (self.slug.parent / "plain").mkdir()
        self.assertEqual(check_minify.explorables_with_sources(self.slug.parent), [self.slug])


if __name__ == "__main__":
    unittest.main()
