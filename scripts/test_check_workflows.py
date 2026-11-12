"""Unit tests for scripts/check_workflows.py. Standard library only, no network.

    python -m unittest discover -s scripts -p "test_*.py"

Each test copies the real workflows, breaks one rule, and checks the check names it.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_workflows as cw  # noqa: E402

CI = ".github/workflows/ci.yml"
ROLLBACK = ".github/workflows/rollback.yml"


class WorkflowCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        for name in cw.DEPLOY_FILES:
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(cw.REPO / name, self.repo / name)

    def tearDown(self):
        self._tmp.cleanup()

    def edit(self, name: str, old: str, new: str) -> None:
        path = self.repo / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assertFlags(self, needle: str) -> None:
        found = cw.problems(self.repo)
        self.assertTrue(any(needle in f for f in found), f"no problem mentioning {needle!r}: {found}")

    def test_the_real_workflows_pass(self):
        self.assertEqual(cw.problems(), [])

    def test_a_deploy_with_a_tag(self):
        self.edit(CI, "--no-traffic --quiet", "--no-traffic --tag=cand --quiet")
        self.assertFlags("names the revision")

    def test_a_deploy_with_a_revision_suffix(self):
        self.edit(CI, '--image="$IMAGE_DIGEST"', '--image="$IMAGE_DIGEST" --revision-suffix=abc')
        self.assertFlags("names the revision")

    def test_gcloud_run_deploy_with_a_tag(self):
        self.edit(ROLLBACK, "      - name: Send 100% of traffic to it\n",
                  "      - name: Redeploy\n        run: gcloud run deploy explorables --tag=x\n"
                  "      - name: Send 100% of traffic to it\n")
        self.assertFlags("names the revision")

    def test_update_tags_on_a_traffic_update_is_allowed(self):
        self.assertIn("--update-tags", (self.repo / CI).read_text(encoding="utf-8"))
        self.assertEqual(cw.problems(self.repo), [])

    def test_a_registry_command_that_needs_delete(self):
        self.edit(CI, 'docker push "$IMAGE"', 'docker push "$IMAGE"\n          gcloud artifacts docker tags add "$IMAGE" "${IMAGE%:*}:live"')
        self.assertFlags("delete permission")

    def test_a_delete_in_the_retag_script(self):
        self.edit("scripts/move_live_tag.py", '["gcloud", "artifacts", "tags", "create"',
                  '["gcloud", "artifacts", "tags", "delete"')
        self.assertFlags("delete permission")

    def test_an_action_pinned_to_a_tag(self):
        self.edit(CI, "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@v7")
        self.assertFlags("not pinned to a full commit SHA")

    def test_an_action_pinned_to_a_short_sha(self):
        self.edit(ROLLBACK, "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@3d3c42e")
        self.assertFlags("not pinned to a full commit SHA")


if __name__ == "__main__":
    unittest.main()
