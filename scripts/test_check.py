"""Unit tests for the explorables gate. Standard library only, no network.

    python -m unittest discover -s scripts -p "test_*.py"

Each test starts from a small explorables tree that passes, breaks one rule, and checks the
gate names it. The tree is built with scripts/build.py, so the tests also prove the build
leaves every README and every src/ folder out.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build  # noqa: E402
import check as ce  # noqa: E402

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Demo</title>
<meta name="description" content="A demo explorable.">
<link rel="canonical" href="https://explorables.kphutt.com/demo/">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="demo.css">
</head>
<body>
<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"></circle></svg>
<button type="button" id="toggle">Toggle</button>
<script type="module" src="demo.js"></script>
</body>
</html>
"""

LANDING = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Explorables</title>
<meta name="description" content="The landing page.">
<link rel="canonical" href="https://explorables.kphutt.com/">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/index.css">
</head>
<body>
<main><a href="/demo/">Demo</a></main>
</body>
</html>
"""

SCRIPT = """import { draw } from "./draw.js";
document.getElementById("toggle").addEventListener("click", () => draw());
"""

STYLE = """@font-face { font-family: Demo; src: url("demo.woff2") format("woff2"); }
body { font-family: Demo, sans-serif; }
"""


class Tree:
    """A passing pages/ tree, its built output, and copies of the server config and Dockerfile."""

    def __init__(self, tmp: Path):
        self.source = tmp / "pages"
        shutil.copytree(ce.SOURCE, self.source, ignore=lambda d, names: [n for n in names if n not in ("README.md", "assets") and Path(d, n).is_dir()])
        # The real landing page links the real explorables and shared assets, which this tree
        # leaves out, so it gets a landing page of its own. test_the_real_tree_passes checks
        # the real one.
        (self.source / "index.html").write_text(LANDING, encoding="utf-8")
        demo = self.source / "demo"
        demo.mkdir()
        (demo / "README.md").write_text("# Demo\n", encoding="utf-8")
        (demo / "index.html").write_text(PAGE, encoding="utf-8")
        (demo / "demo.js").write_text(SCRIPT, encoding="utf-8")
        (demo / "draw.js").write_text("export function draw() {}\n", encoding="utf-8")
        (demo / "demo.css").write_text(STYLE, encoding="utf-8")
        (demo / "demo.woff2").write_bytes(b"wOF2")
        # Readable sources, which the build leaves out.
        (demo / "src").mkdir()
        (demo / "src" / "demo.js").write_text(SCRIPT, encoding="utf-8")
        self.root = tmp / "public-explorables"
        self.server = tmp / "server"
        self.server.mkdir()
        self.config = self.server / "sws.toml"
        shutil.copy(ce.CONFIG, self.config)
        self.dockerfile = tmp / "Dockerfile"
        shutil.copy(ce.DOCKERFILE, self.dockerfile)

    def build(self) -> None:
        build.build(self.source, self.root)

    def failures(self) -> list:
        return ce.check(self.root, self.source, self.config, self.dockerfile)

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        assert old in text, f"{old!r} not in {path}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")


class GateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = Tree(Path(self._tmp.name))
        self.tree.build()

    def tearDown(self):
        self._tmp.cleanup()

    def page(self) -> Path:
        return self.tree.root / "demo" / "index.html"

    def assertFails(self, needle: str) -> None:
        failures = self.tree.failures()
        self.assertTrue(any(needle in f for f in failures), f"no failure mentioning {needle!r}: {failures}")


class Passing(GateTest):
    def test_the_fixture_passes(self):
        self.assertEqual(self.tree.failures(), [])

    def test_the_real_tree_passes(self):
        with tempfile.TemporaryDirectory() as out:
            build.build(ce.SOURCE, Path(out) / "built")
            self.assertEqual(ce.check(Path(out) / "built"), [])

    def test_the_build_leaves_readmes_out(self):
        self.assertTrue((self.tree.source / "demo" / "README.md").is_file())
        self.assertFalse((self.tree.root / "demo" / "README.md").exists())
        self.assertTrue((self.tree.root / "demo" / "index.html").is_file())

    def test_the_build_leaves_sources_out(self):
        self.assertTrue((self.tree.source / "demo" / "src" / "demo.js").is_file())
        self.assertFalse((self.tree.root / "demo" / "src").exists())


class JsonLd(GateTest):
    """JSON-LD is the one <script> with a body a page may carry, and only as plain data."""

    GOOD = '{"@context":"https://schema.org","@type":"CreativeWork","name":"Demo"}'

    def add(self, html: str) -> None:
        self.tree.edit(self.page(), "</head>", html + "</head>")

    def test_a_json_ld_object_passes(self):
        self.add(f'<script type="application/ld+json">{self.GOOD}</script>')
        self.assertEqual(self.tree.failures(), [])

    def test_a_json_ld_array_passes(self):
        self.add(f"<script type=application/ld+json>[{self.GOOD}]</script>")
        self.assertEqual(self.tree.failures(), [])

    def test_javascript_typed_script_still_fails(self):
        self.add('<script type="text/javascript">alert(1)</script>')
        self.assertFails("inline script")

    def test_a_type_that_only_contains_ld_json_fails(self):
        self.add('<script type="application/ld+json+js">alert(1)</script>')
        self.assertFails("inline script")

    def test_invalid_json_fails(self):
        self.add('<script type="application/ld+json">alert(1)</script>')
        self.assertFails("is not valid JSON")

    def test_a_json_scalar_fails(self):
        self.add('<script type="application/ld+json">"text"</script>')
        self.assertFails("not a JSON object or array")

    def test_a_second_type_attribute_fails(self):
        self.add(f'<script type="text/javascript" type="application/ld+json">{self.GOOD}</script>')
        self.assertFails("more than one type attribute")

    def test_a_second_type_attribute_after_a_quote_fails(self):
        self.add(f'<script id="x"type="text/javascript" type="application/ld+json">{self.GOOD}</script>')
        self.assertFails("more than one type attribute")

    def test_a_src_attribute_fails(self):
        self.add(f'<script type="application/ld+json" src="a.json">{self.GOOD}</script>')
        self.assertFails("has a src attribute")

    def test_a_comment_opener_fails(self):
        self.add('<script type="application/ld+json">{"a":"<!--"}</script>')
        self.assertFails("changes where the element ends")

    def test_a_script_tag_inside_fails(self):
        self.add('<script type="application/ld+json">{"a":"<SCRIPT"}</script>')
        self.assertFails("changes where the element ends")

    def test_data_type_attribute_is_not_a_second_type(self):
        self.add(f'<script data-type="x" type="application/ld+json">{self.GOOD}</script>')
        self.assertEqual(self.tree.failures(), [])


class InlineCode(GateTest):
    def test_inline_script(self):
        self.tree.edit(self.page(), "</body>", "<script>alert(1)</script></body>")
        self.assertFails("inline script")

    def test_script_with_src_and_a_body(self):
        self.tree.edit(self.page(), 'src="demo.js"></script>', 'src="demo.js">alert(1)</script>')
        self.assertFails("demo/index.html: external script")

    def test_unclosed_script(self):
        self.tree.edit(self.page(), "</body>", "<script src=demo.js></body>")
        self.assertFails("without its </script>")

    def test_style_element(self):
        self.tree.edit(self.page(), "</head>", "<style>body{}</style></head>")
        self.assertFails("<style> element")

    def test_style_attribute(self):
        self.tree.edit(self.page(), '<button type="button"', '<button style="color:red" type="button"')
        self.assertFails("style= attribute")

    def test_event_handler(self):
        self.tree.edit(self.page(), '<button type="button"', '<button onclick="go()" type="button"')
        self.assertFails("onclick=")

    def test_event_handler_in_svg(self):
        self.tree.edit(self.page(), "<circle ", "<circle onload=go() ")
        self.assertFails("onload=")

    def test_styles_set_through_the_cssom_pass(self):
        # el.style.cssText and a data-style hook the script reads are not style= attributes.
        self.tree.edit(self.page(), '<button type="button"', '<button data-style="color: red" data-a-style="x" type="button"')
        self.tree.edit(self.tree.root / "demo" / "demo.js", "draw());", 'draw()); el.style.cssText = "color: red"; el.setAttribute("data-style", "a");')
        self.assertEqual(self.tree.failures(), [])

    def test_style_attribute_in_capitals(self):
        self.tree.edit(self.page(), '<button type="button"', '<button STYLE="color:red" type="button"')
        self.assertFails("style= attribute")

    def test_style_attribute_after_a_quote(self):
        self.tree.edit(self.page(), '<button type="button"', '<button type="button"style="color:red"')
        self.assertFails("style= attribute")

    def test_style_attribute_in_svg(self):
        self.tree.edit(self.page(), "<circle ", '<circle style="fill:red" ')
        self.assertFails("style= attribute")

    def test_style_attribute_in_an_svg_file(self):
        (self.tree.root / "demo" / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:red"/></svg>', encoding="utf-8")
        self.assertFails("demo/icon.svg: inline style= attribute")

    def test_javascript_url(self):
        self.tree.edit(self.page(), "</body>", '<a href="javascript:go()">x</a></body>')
        self.assertFails("javascript: URL")


class OtherOrigins(GateTest):
    def test_script_from_another_origin(self):
        self.tree.edit(self.page(), 'src="demo.js"', 'src="https://cdn.example.com/x.js"')
        self.assertFails("from another origin")

    def test_protocol_relative_script(self):
        self.tree.edit(self.page(), 'src="demo.js"', 'src="//cdn.example.com/x.js"')
        self.assertFails("from another origin")

    def test_script_by_absolute_url_on_this_origin(self):
        self.tree.edit(self.page(), 'src="demo.js"', f'src="{ce.ORIGIN}/demo/demo.js"')
        self.assertFails("absolute URL")

    def test_module_import_from_another_origin(self):
        self.tree.edit(self.tree.root / "demo" / "demo.js", '"./draw.js"', '"https://cdn.example.com/draw.js"')
        self.assertFails("from another origin")

    def test_dynamic_import_from_another_origin(self):
        self.tree.edit(self.tree.root / "demo" / "demo.js", "draw());", 'import("https://cdn.example.com/x.js"));')
        self.assertFails("from another origin")

    def test_stylesheet_from_another_origin(self):
        self.tree.edit(self.page(), 'href="demo.css"', 'href="https://fonts.example.com/x.css"')
        self.assertFails("from another origin")

    def test_font_from_another_origin(self):
        self.tree.edit(self.tree.root / "demo" / "demo.css", 'url("demo.woff2")', 'url("https://fonts.example.com/x.woff2")')
        self.assertFails("from another origin")

    def test_image_from_another_origin(self):
        self.tree.edit(self.page(), "</body>", '<img src="https://img.example.com/x.png" alt=""></body>')
        self.assertFails("from another origin")

    def test_css_import(self):
        self.tree.edit(self.tree.root / "demo" / "demo.css", "body {", '@import "other.css";\nbody {')
        self.assertFails("@import")

    def test_a_bundled_font_is_allowed(self):
        # @font-face is allowed here (the policy has font-src 'self'), with a same-origin url().
        self.assertEqual(self.tree.failures(), [])


class Findable(GateTest):
    def test_a_page_with_noindex(self):
        self.tree.edit(self.page(), "<title>", '<meta name="robots" content="noindex"><title>')
        self.assertFails("keeps the page out of search")

    def test_a_page_with_robots_none(self):
        self.tree.edit(self.page(), "<title>", '<meta name="robots" content="none"><title>')
        self.assertFails("keeps the page out of search")

    def test_a_page_with_noindex_for_one_crawler(self):
        self.tree.edit(self.page(), "<title>", "<meta name=googlebot content='follow, NoIndex'><title>")
        self.assertFails("keeps the page out of search")

    def test_the_landing_page_with_noindex(self):
        self.tree.edit(self.tree.root / "index.html", "<title>", '<meta name="robots" content="noindex"><title>')
        self.assertFails("index.html: a robots meta tag says noindex")

    def test_nofollow_alone_is_allowed(self):
        self.tree.edit(self.page(), "<title>", '<meta name="robots" content="nofollow"><title>')
        self.assertEqual(self.tree.failures(), [])

    def test_the_404_page_must_say_noindex(self):
        self.tree.edit(self.tree.root / "404.html", '<meta name="robots" content="noindex">', "")
        self.assertFails("404.html: no <meta")

    def test_missing_title(self):
        self.tree.edit(self.page(), "<title>Demo</title>", "")
        self.assertFails("no <title>")

    def test_empty_title(self):
        self.tree.edit(self.page(), "<title>Demo</title>", "<title> </title>")
        self.assertFails("no <title>")

    def test_missing_description(self):
        self.tree.edit(self.page(), '<meta name="description" content="A demo explorable.">', "")
        self.assertFails("description")

    def test_empty_description(self):
        self.tree.edit(self.page(), 'content="A demo explorable."', 'content=" "')
        self.assertFails("description")

    def test_two_descriptions(self):
        self.tree.edit(self.page(), "<title>", '<meta name="description" content="Another."><title>')
        self.assertFails("description")

    def test_missing_canonical(self):
        self.tree.edit(self.page(), '<link rel="canonical" href="https://explorables.kphutt.com/demo/">', "")
        self.assertFails("canonical link is []")

    def test_canonical_to_another_page(self):
        self.tree.edit(self.page(), 'href="https://explorables.kphutt.com/demo/"', 'href="https://explorables.kphutt.com/"')
        self.assertFails("canonical link")

    def test_canonical_on_another_host(self):
        self.tree.edit(self.page(), 'href="https://explorables.kphutt.com/demo/"', 'href="https://kphutt.com/demo/"')
        self.assertFails("canonical link")

    def test_relative_canonical(self):
        self.tree.edit(self.page(), 'href="https://explorables.kphutt.com/demo/"', 'href="/demo/"')
        self.assertFails("canonical link")


class Generated(GateTest):
    """What scripts/build.py writes: robots.txt, the sitemap's dates and llms.txt."""

    def test_robots_welcomes_every_use(self):
        text = (self.tree.root / "robots.txt").read_text(encoding="utf-8")
        self.assertEqual(text.splitlines(), [
            "User-agent: *",
            "Allow: /",
            "",
            "Sitemap: https://explorables.kphutt.com/sitemap.xml",
        ])

    def test_llms_txt_names_the_author_and_lists_each_explorable(self):
        text = (self.tree.root / "llms.txt").read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(lines[0], "# Explorables")
        self.assertTrue(lines[2].startswith("> ") and len(lines[2]) > 2, lines[2])
        self.assertIn("Made by Karsten Huttelmaier (kphutt).", text)
        self.assertIn(build.AUTHOR_URL, text)
        for url in build.PROFILES.values():
            self.assertIn(f"]({url})", text)
        self.assertIn("- [Demo](https://explorables.kphutt.com/demo/): A demo explorable.", lines)
        self.assertNotIn("](https://explorables.kphutt.com/)", text)

    def test_llms_txt_without_a_description(self):
        self.tree.edit(self.tree.source / "demo" / "index.html", '<meta name="description" content="A demo explorable.">', "")
        self.tree.build()
        self.assertIn("- [Demo](https://explorables.kphutt.com/demo/)",
                      (self.tree.root / "llms.txt").read_text(encoding="utf-8").splitlines())

    def test_a_hand_written_llms_txt_is_refused(self):
        (self.tree.source / "llms.txt").write_text("# x", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.tree.build()

    def test_a_missing_llms_txt_fails(self):
        (self.tree.root / "llms.txt").unlink()
        self.assertFails("llms.txt")

    def test_the_sitemap_carries_lastmod_when_known(self):
        text = build.sitemap_xml(["/", "/demo/"], {"/": "2026-01-02T03:04:05-08:00", "/demo/": ""})
        self.assertIn("<loc>https://explorables.kphutt.com/</loc><lastmod>2026-01-02T03:04:05-08:00</lastmod>", text)
        self.assertIn("<loc>https://explorables.kphutt.com/demo/</loc></url>", text)

    def test_last_changed_reads_git_for_a_committed_page(self):
        self.assertRegex(build.last_changed(build.page_files(build.SOURCE, "/")), build.GIT_DATE.pattern)

    def test_last_changed_is_empty_outside_the_repository(self):
        self.assertEqual(build.last_changed(build.page_files(self.tree.source, "/demo/")), "")

    def test_every_page_describes_the_same_author(self):
        # The pages' JSON-LD is written by hand, so this keeps its Person record the same
        # as build.py's, and the same as kphutt.com's (same @id, same profiles).
        import json
        import re
        for path in build.page_paths(build.SOURCE):
            page = build.SOURCE / path.strip("/") / "index.html"
            blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
            nodes = [n for b in blocks for n in json.loads(b).get("@graph", [])]
            people = [n for n in nodes if n.get("@type") == "Person"]
            self.assertEqual(len(people), 1, page)
            self.assertEqual(people[0]["@id"], build.AUTHOR_ID, page)
            self.assertEqual(people[0]["name"], build.AUTHOR, page)
            self.assertEqual(people[0]["description"], build.AUTHOR_LINE, page)
            self.assertEqual(people[0]["sameAs"], list(build.PROFILES.values()), page)
            authored = [n for n in nodes if n.get("@type") != "Person"]
            self.assertTrue(authored and all(n.get("author") == {"@id": build.AUTHOR_ID} for n in authored), page)

    def test_last_changed_ignores_output_that_is_not_a_date(self):
        from unittest import mock
        fake = mock.Mock(returncode=0, stdout="fatal: not a date")
        with mock.patch.object(build.subprocess, "run", return_value=fake):
            self.assertEqual(build.last_changed([build.SOURCE]), "")

    def test_page_summary_is_plain_text(self):
        self.tree.edit(self.tree.source / "demo" / "index.html", "<title>Demo</title>", "<title>Demo &amp;\n  more</title>")
        self.assertEqual(build.page_summary(self.tree.source / "demo" / "index.html"), ("Demo & more", "A demo explorable."))

    def test_the_landing_page_is_its_own_two_files(self):
        self.assertEqual(build.page_files(build.SOURCE, "/"), [build.SOURCE / "index.html", build.SOURCE / "index.css"])
        self.assertEqual(build.page_files(build.SOURCE, "/demo/"), [build.SOURCE / "demo"])


class Discovery(GateTest):
    def sitemap(self) -> Path:
        return self.tree.root / "sitemap.xml"

    def test_the_build_lists_every_explorable(self):
        text = self.sitemap().read_text(encoding="utf-8")
        self.assertIn("<loc>https://explorables.kphutt.com/</loc>", text)
        self.assertIn("<loc>https://explorables.kphutt.com/demo/</loc>", text)
        self.assertIn("Sitemap: https://explorables.kphutt.com/sitemap.xml",
                      (self.tree.root / "robots.txt").read_text(encoding="utf-8"))

    def test_the_build_refuses_a_hand_written_sitemap(self):
        (self.tree.source / "sitemap.xml").write_text("<urlset/>", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.tree.build()

    def test_an_explorable_missing_from_the_sitemap(self):
        self.tree.edit(self.sitemap(), "  <url><loc>https://explorables.kphutt.com/demo/</loc></url>\n", "")
        self.assertFails("does not list https://explorables.kphutt.com/demo/")

    def test_the_landing_page_missing_from_the_sitemap(self):
        self.tree.edit(self.sitemap(), "  <url><loc>https://explorables.kphutt.com/</loc></url>\n", "")
        self.assertFails("does not list https://explorables.kphutt.com/")

    def test_a_path_that_is_not_built(self):
        self.tree.edit(self.sitemap(), "</urlset>", "  <url><loc>https://explorables.kphutt.com/gone/</loc></url>\n</urlset>")
        self.assertFails("not a page in the build")

    def test_a_file_that_is_not_a_page(self):
        self.tree.edit(self.sitemap(), "</urlset>", "  <url><loc>https://explorables.kphutt.com/demo/demo.js</loc></url>\n</urlset>")
        self.assertFails("not a page in the build")

    def test_a_page_without_its_trailing_slash(self):
        # /demo only redirects to /demo/, so it is not the page's URL.
        self.tree.edit(self.sitemap(), "https://explorables.kphutt.com/demo/</loc>", "https://explorables.kphutt.com/demo</loc>")
        self.assertFails("not a page in the build")

    def test_a_url_on_another_host(self):
        self.tree.edit(self.sitemap(), "</urlset>", "  <url><loc>https://kphutt.com/</loc></url>\n</urlset>")
        self.assertFails("not an absolute URL on")

    def test_a_relative_url(self):
        self.tree.edit(self.sitemap(), "</urlset>", "  <url><loc>/demo/</loc></url>\n</urlset>")
        self.assertFails("not an absolute URL on")

    def test_a_url_listed_twice(self):
        self.tree.edit(self.sitemap(), "</urlset>", "  <url><loc>https://explorables.kphutt.com/demo/</loc></url>\n</urlset>")
        self.assertFails("twice")

    def test_invalid_xml(self):
        self.sitemap().write_text("<urlset", encoding="utf-8")
        self.assertFails("not valid XML")

    def test_missing_sitemap(self):
        self.sitemap().unlink()
        self.assertFails("sitemap.xml missing")

    def test_missing_robots_txt(self):
        (self.tree.root / "robots.txt").unlink()
        self.assertFails("robots.txt missing")

    def test_robots_txt_without_the_sitemap(self):
        self.tree.edit(self.tree.root / "robots.txt", "Sitemap: https://explorables.kphutt.com/sitemap.xml\n", "")
        self.assertFails("no 'Sitemap:")

    def test_robots_txt_blocking_everything(self):
        self.tree.edit(self.tree.root / "robots.txt", "Allow: /", "Disallow: /")
        self.assertFails("keeps pages out of search")

    def test_robots_txt_blocking_one_explorable(self):
        self.tree.edit(self.tree.root / "robots.txt", "Allow: /", "Allow: /\nDisallow: /demo/")
        self.assertFails("keeps pages out of search")


class Layout(GateTest):
    def test_explorable_without_a_readme(self):
        (self.tree.source / "demo" / "README.md").unlink()
        self.assertFails("no README.md")

    def test_explorable_without_an_index(self):
        (self.tree.source / "demo" / "index.html").unlink()
        self.assertFails("no index.html")

    def test_a_folder_that_is_not_a_slug(self):
        shutil.copytree(self.tree.source / "demo", self.tree.source / "Demo_2")
        self.assertFails("not a slug")

    def test_a_readme_in_the_output(self):
        (self.tree.root / "demo" / "README.md").write_text("# Demo\n", encoding="utf-8")
        self.assertFails("would serve it")

    def test_a_readme_with_another_name_in_the_output(self):
        (self.tree.root / "demo" / "readme.txt").write_text("x\n", encoding="utf-8")
        self.assertFails("would serve it")

    def test_dot_file(self):
        (self.tree.root / "demo" / ".env").write_text("x\n", encoding="utf-8")
        self.assertFails("hidden files")

    def test_dot_folder(self):
        (self.tree.root / ".git").mkdir()
        (self.tree.root / ".git" / "config").write_text("x\n", encoding="utf-8")
        self.assertFails("hidden files")

    def test_missing_404_page(self):
        (self.tree.root / "404.html").unlink()
        self.assertFails("404.html missing")

    def test_broken_internal_reference(self):
        self.tree.edit(self.page(), 'href="demo.css"', 'href="gone.css"')
        self.assertFails("broken internal reference")

    def test_base_image_without_a_digest(self):
        self.tree.edit(self.tree.dockerfile, "3.0.0-beta.2@sha256:", "3.0.0-beta.2 # sha256:")
        self.assertFails("pinned by version and digest")

    def test_base_image_without_a_version(self):
        self.tree.edit(self.tree.dockerfile, "static-web-server:3.0.0-beta.2@", "static-web-server@")
        self.assertFails("pinned by version and digest")

    def test_another_base_image(self):
        self.tree.edit(self.tree.dockerfile, "ghcr.io/static-web-server/static-web-server:", "docker.io/library/nginx:")
        self.assertFails("pinned by version and digest")

    def test_two_build_stages(self):
        self.tree.edit(self.tree.dockerfile, "COPY server/", "FROM scratch\nCOPY server/")
        self.assertFails("pinned by version and digest")


class Shared(GateTest):
    """pages/assets/ holds files the pages share. It is not an explorable."""

    def setUp(self):
        super().setUp()
        (self.tree.source / "assets").mkdir(exist_ok=True)
        (self.tree.source / "assets" / "shared.woff2").write_bytes(b"wOF2")
        self.tree.build()

    def test_it_needs_no_index_or_readme(self):
        self.assertEqual(self.tree.failures(), [])

    def test_it_is_not_in_the_sitemap(self):
        self.assertNotIn("/assets/", (self.tree.root / "sitemap.xml").read_text(encoding="utf-8"))

    def test_a_page_in_it_fails(self):
        (self.tree.source / "assets" / "index.html").write_text(PAGE, encoding="utf-8")
        self.tree.build()
        self.assertFails("is for shared files, not pages")

    def test_a_page_deeper_in_it_fails(self):
        (self.tree.source / "assets" / "x").mkdir()
        (self.tree.source / "assets" / "x" / "a.html").write_text(PAGE, encoding="utf-8")
        self.tree.build()
        self.assertFails("is for shared files, not pages: assets/x/a.html")

    def test_a_page_loading_a_shared_font_passes(self):
        self.tree.edit(self.tree.root / "demo" / "demo.css", 'url("demo.woff2")', 'url("../assets/shared.woff2")')
        self.assertEqual(self.tree.failures(), [])


class Icon(GateTest):
    def test_a_page_without_an_icon(self):
        self.tree.edit(self.page(), '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n', "")
        self.assertFails('demo/index.html: no <link rel="icon"')

    def test_the_404_page_without_an_icon(self):
        self.tree.edit(self.tree.root / "404.html", '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n', "")
        self.assertFails('404.html: no <link rel="icon"')

    def test_an_icon_link_without_an_href(self):
        self.tree.edit(self.page(), '<link rel="icon" href="/assets/favicon.svg"', '<link rel="icon"')
        self.assertFails('demo/index.html: no <link rel="icon"')

    def test_an_icon_that_is_missing(self):
        self.tree.edit(self.page(), 'href="/assets/favicon.svg"', 'href="/assets/gone.svg"')
        self.assertFails("broken internal reference /assets/gone.svg")

    def test_a_shortcut_icon_counts(self):
        self.tree.edit(self.page(), '<link rel="icon"', '<link rel="shortcut icon"')
        self.assertEqual(self.tree.failures(), [])


class Sources(GateTest):
    """Readable sources and the npm toolchain are for the repository, never served."""

    def test_a_source_folder_in_the_output(self):
        shutil.copytree(self.tree.source / "demo" / "src", self.tree.root / "demo" / "src")
        self.assertFails("demo/src")

    def test_a_source_folder_deeper_down_is_copied_and_fails(self):
        (self.tree.source / "demo" / "lib" / "src").mkdir(parents=True)
        (self.tree.source / "demo" / "lib" / "src" / "x.js").write_text("x\n", encoding="utf-8")
        self.tree.build()
        self.assertFails("demo/lib/src")

    def test_a_file_named_src(self):
        shutil.rmtree(self.tree.source / "demo" / "src")
        (self.tree.source / "demo" / "src").write_text("x\n", encoding="utf-8")
        self.tree.build()
        self.assertFails("demo/src: not a folder")

    def test_node_modules_in_the_output(self):
        (self.tree.root / "demo" / "node_modules" / "esbuild").mkdir(parents=True)
        self.assertFails("demo/node_modules")

    def test_package_json_in_the_output(self):
        (self.tree.root / "demo" / "package.json").write_text("{}\n", encoding="utf-8")
        self.assertFails("demo/package.json")

    def test_a_lockfile_in_the_output(self):
        (self.tree.root / "package-lock.json").write_text("{}\n", encoding="utf-8")
        self.assertFails("package-lock.json")

    def test_a_source_map_in_the_output(self):
        (self.tree.root / "demo" / "demo.js.map").write_text("{}\n", encoding="utf-8")
        self.assertFails("demo/demo.js.map")


CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; "
       "connect-src https://explorables.kphutt.com/robots.txt; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; "
       "require-trusted-types-for 'script'; trusted-types 'none'; upgrade-insecure-requests")


class Headers(GateTest):
    def csp(self, old: str, new: str) -> None:
        self.assertIn(CSP, self.tree.config.read_text(encoding="utf-8"))
        self.tree.edit(self.tree.config, CSP, CSP.replace(old, new, 1))

    def test_the_brief_policy_is_what_ships(self):
        self.assertIn(f'Content-Security-Policy = "{CSP}"', ce.CONFIG.read_text(encoding="utf-8"))

    def test_unsafe_inline(self):
        self.csp("script-src 'self'", "script-src 'self' 'unsafe-inline'")
        self.assertFails("script-src allows 'unsafe-inline'")

    def test_unsafe_eval(self):
        self.csp("script-src 'self'", "script-src 'self' 'unsafe-eval'")
        self.assertFails("script-src allows 'unsafe-eval'")

    def test_hash(self):
        self.csp("script-src 'self'", "script-src 'self' 'sha256-abc='")
        self.assertFails("script-src allows 'sha256-abc='")

    def test_nonce(self):
        self.csp("script-src 'self'", "script-src 'self' 'nonce-abc'")
        self.assertFails("script-src allows 'nonce-abc'")

    def test_another_origin(self):
        self.csp("script-src 'self'", "script-src 'self' https://cdn.example.com")
        self.assertFails("script-src allows https://cdn.example.com")

    def test_wildcard(self):
        self.csp("img-src 'self'", "img-src *")
        self.assertFails("img-src allows *")

    def test_default_src_self(self):
        self.csp("default-src 'none'", "default-src 'self'")
        self.assertFails("default-src allows 'self'")

    def test_connect_src_self(self):
        self.csp(f"connect-src {ce.ROBOTS_URL}", "connect-src 'self'")
        self.assertFails("connect-src allows 'self'")

    def test_connect_src_another_origin(self):
        self.csp(f"connect-src {ce.ROBOTS_URL}", "connect-src https://api.example.com")
        self.assertFails("connect-src allows https://api.example.com")

    def test_connect_src_none_passes(self):
        self.csp(f"connect-src {ce.ROBOTS_URL}", "connect-src 'none'")
        self.assertEqual(self.tree.failures(), [])

    def test_the_config_names_exactly_the_robots_url(self):
        self.assertEqual(ce.ROBOTS_URL, "https://explorables.kphutt.com/robots.txt")
        self.assertIn(f"connect-src {ce.ROBOTS_URL};", self.tree.config.read_text(encoding="utf-8"))
        self.assertEqual(self.tree.failures(), [])

    def test_connect_src_broader_than_robots_txt(self):
        original = self.tree.config.read_text(encoding="utf-8")
        for broader in (
            "'self'",
            "*",
            "https:",
            "https://explorables.kphutt.com",
            "https://explorables.kphutt.com/",
            "https://explorables.kphutt.com/robots.txt/",
            "https://explorables.kphutt.com/*",
            "https://*.kphutt.com/robots.txt",
            "http://explorables.kphutt.com/robots.txt",
            "explorables.kphutt.com/robots.txt",
            "https://explorables.kphutt.com/sitemap.xml",
            "https://kphutt.com/robots.txt",
        ):
            with self.subTest(broader=broader):
                self.tree.config.write_text(original.replace(f"connect-src {ce.ROBOTS_URL}", f"connect-src {broader}"), encoding="utf-8")
                self.assertFails(f"connect-src allows {broader}")

    def test_connect_src_left_out(self):
        self.csp(f"connect-src {ce.ROBOTS_URL}; ", "")
        self.assertFails("connect-src is missing")

    def test_an_unlisted_fetch_directive(self):
        self.csp("form-action 'none'", "form-action 'none'; script-src-elem 'self'")
        self.assertFails("script-src-elem allows 'self'")

    def test_missing_directive(self):
        self.csp("frame-ancestors 'none'; ", "")
        self.assertFails("frame-ancestors is missing")

    def test_missing_trusted_types(self):
        self.csp("; require-trusted-types-for 'script'", "")
        self.assertFails("require-trusted-types-for is missing")

    def test_missing_trusted_types_policy_list(self):
        self.csp("; trusted-types 'none'", "")
        self.assertFails("trusted-types is missing")

    def test_trusted_types_policy_allowed(self):
        self.csp("trusted-types 'none'", "trusted-types default")
        self.assertFails("must have trusted-types 'none'")

    def test_trusted_types_with_duplicates_allowed(self):
        self.csp("trusted-types 'none'", "trusted-types 'none' 'allow-duplicates'")
        self.assertFails("must have trusted-types 'none'")

    def test_missing_upgrade_insecure_requests(self):
        self.csp("; upgrade-insecure-requests", "")
        self.assertFails("upgrade-insecure-requests is missing")

    def test_upgrade_insecure_requests_with_a_value(self):
        self.csp("upgrade-insecure-requests", "upgrade-insecure-requests x")
        self.assertFails("must have upgrade-insecure-requests")

    def test_trusted_types_with_another_value(self):
        # Browsers ignore a value other than 'script', which turns Trusted Types off.
        self.csp("require-trusted-types-for 'script'", "require-trusted-types-for 'none'")
        self.assertFails("require-trusted-types-for 'script'")

    def test_missing_policy(self):
        self.tree.edit(self.tree.config, "Content-Security-Policy = ", "X-Not-A-Policy = ")
        self.assertFails("no Content-Security-Policy")

    def test_noindex_header(self):
        self.tree.edit(self.tree.config, 'Cache-Control = "public, max-age=300"', 'Cache-Control = "public, max-age=300"\nX-Robots-Tag = "noindex"')
        self.assertFails("would keep every page out of search")

    def test_robots_none_header(self):
        self.tree.edit(self.tree.config, 'Cache-Control = "public, max-age=300"', 'Cache-Control = "public, max-age=300"\nX-Robots-Tag = "none"')
        self.assertFails("would keep every page out of search")

    def test_noindex_header_on_a_narrower_rule(self):
        self.tree.edit(self.tree.config, 'headers.Cache-Control = "public, max-age=2592000"\n\n[[advanced.headers]]\nsource = "**/favicon.svg"',
                       'headers.X-Robots-Tag = "noindex"\n\n[[advanced.headers]]\nsource = "**/favicon.svg"')
        self.assertFails("override the catch-all")

    def test_weaker_referrer_policy(self):
        self.tree.edit(self.tree.config, '"no-referrer"', '"strict-origin-when-cross-origin"')
        self.assertFails("Referrer-Policy")

    def test_missing_nosniff(self):
        self.tree.edit(self.tree.config, 'X-Content-Type-Options = "nosniff"\n', "")
        self.assertFails("X-Content-Type-Options")

    def test_missing_coop(self):
        self.tree.edit(self.tree.config, 'Cross-Origin-Opener-Policy = "same-origin"\n', "")
        self.assertFails("Cross-Origin-Opener-Policy")

    def test_missing_corp(self):
        self.tree.edit(self.tree.config, 'Cross-Origin-Resource-Policy = "same-origin"\n', "")
        self.assertFails("Cross-Origin-Resource-Policy")

    def test_missing_coep(self):
        self.tree.edit(self.tree.config, 'Cross-Origin-Embedder-Policy = "require-corp"\n', "")
        self.assertFails("Cross-Origin-Embedder-Policy")

    def test_weaker_coep(self):
        self.tree.edit(self.tree.config, '"require-corp"', '"unsafe-none"')
        self.assertFails("Cross-Origin-Embedder-Policy")

    def test_missing_x_frame_options(self):
        self.tree.edit(self.tree.config, 'X-Frame-Options = "DENY"\n', "")
        self.assertFails("X-Frame-Options")

    def test_weaker_x_frame_options(self):
        self.tree.edit(self.tree.config, 'X-Frame-Options = "DENY"', 'X-Frame-Options = "SAMEORIGIN"')
        self.assertFails("X-Frame-Options")

    def test_hsts_without_include_subdomains(self):
        self.tree.edit(self.tree.config, '"max-age=63072000; includeSubDomains"', '"max-age=63072000"')
        self.assertFails("must have includeSubDomains")

    def test_hsts_preload(self):
        self.tree.edit(self.tree.config, '"max-age=63072000; includeSubDomains"', '"max-age=63072000; includeSubDomains; preload"')
        self.assertFails("has preload")

    def test_hsts_too_short(self):
        self.tree.edit(self.tree.config, '"max-age=63072000; includeSubDomains"', '"max-age=600; includeSubDomains"')
        self.assertFails("max-age must be at least")

    def test_compression_off(self):
        self.tree.edit(self.tree.config, "compression = true", "compression = false")
        self.assertFails("compression")

    def test_idle_timeout_left_out(self):
        self.tree.edit(self.tree.config, "idle-timeout = 30\n", "")
        self.assertFails("idle-timeout must be set")

    def test_idle_timeout_zero_disables_it(self):
        self.tree.edit(self.tree.config, "idle-timeout = 30", "idle-timeout = 0")
        self.assertFails("idle-timeout must be set")

    def test_idle_timeout_as_a_string(self):
        self.tree.edit(self.tree.config, "idle-timeout = 30", 'idle-timeout = "30"')
        self.assertFails("idle-timeout must be set")

    def test_idle_timeout_as_a_boolean(self):
        # TOML true is not a number of seconds, though Python counts it as the integer 1.
        self.tree.edit(self.tree.config, "idle-timeout = 30", "idle-timeout = true")
        self.assertFails("idle-timeout must be set")

    def test_idle_timeout_of_one_second_passes(self):
        self.tree.edit(self.tree.config, "idle-timeout = 30", "idle-timeout = 1")
        self.assertEqual(self.tree.failures(), [])

    def test_compression_left_out(self):
        self.tree.edit(self.tree.config, "compression = true\n", "")
        self.assertFails("compression")

    def test_short_font_cache(self):
        self.tree.edit(self.tree.config, 'source = "**/*.{woff2,woff}"\nheaders.Cache-Control = "public, max-age=2592000"',
                       'source = "**/*.{woff2,woff}"\nheaders.Cache-Control = "public, max-age=86400"')
        self.assertFails("'**/*.{woff2,woff}' with Cache-Control max-age")

    def test_short_favicon_cache(self):
        self.tree.edit(self.tree.config, 'source = "**/favicon.svg"\nheaders.Cache-Control = "public, max-age=2592000"',
                       'source = "**/favicon.svg"\nheaders.Cache-Control = "public, max-age=300"')
        self.assertFails("'**/favicon.svg' with Cache-Control max-age")

    def test_missing_favicon_rule(self):
        self.tree.edit(self.tree.config, 'source = "**/favicon.svg"', 'source = "**/favicon.ico"')
        self.assertFails("'**/favicon.svg' with Cache-Control max-age")

    def test_immutable_on_an_unhashed_name(self):
        self.tree.edit(self.tree.config, 'source = "**/*.{woff2,woff}"\nheaders.Cache-Control = "public, max-age=2592000"',
                       'source = "**/*.{woff2,woff}"\nheaders.Cache-Control = "public, max-age=31536000, immutable"')
        self.assertFails("is immutable")

    def test_immutable_on_the_catch_all(self):
        self.tree.edit(self.tree.config, 'Cache-Control = "public, max-age=300"', 'Cache-Control = "public, max-age=300, immutable"')
        self.assertFails("is immutable")

    def test_permissions_policy_differs_from_kphutt_com(self):
        self.tree.edit(self.tree.config, "camera=(), ", "")
        self.assertFails("Permissions-Policy must equal")

    def test_missing_cache_control(self):
        self.tree.edit(self.tree.config, 'Cache-Control = "public, max-age=300"\n', "")
        self.assertFails("Cache-Control")

    def test_a_narrower_rule_overriding_a_security_header(self):
        self.tree.edit(self.tree.config, 'source = "**/favicon.svg"\nheaders.Cache-Control = "public, max-age=2592000"',
                       'source = "**/favicon.svg"\nheaders.Content-Security-Policy = "default-src *"')
        self.assertFails("override the catch-all")

    def test_builtin_security_headers_on(self):
        self.tree.edit(self.tree.config, "security-headers = false", "security-headers = true")
        self.assertFails("security-headers must be false")

    def test_no_404_page_configured(self):
        self.tree.edit(self.tree.config, 'page404 = "404.html"\n', "")
        self.assertFails("page404")

    def test_hidden_files_served(self):
        self.tree.edit(self.tree.config, "include-hidden = false", "include-hidden = true")
        self.assertFails("include-hidden")

    def test_the_v2_hidden_files_key_does_not_count(self):
        # v3 ignores ignore-hidden-files with only a warning, so the old name must not pass.
        self.tree.edit(self.tree.config, "include-hidden = false", "ignore-hidden-files = true")
        self.assertFails("include-hidden must be False")

    def test_directory_listing(self):
        self.tree.edit(self.tree.config, "directory-listing = false", "directory-listing = true")
        self.assertFails("directory-listing")


if __name__ == "__main__":
    unittest.main()
