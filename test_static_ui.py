import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


class StaticUiTests(unittest.TestCase):
    def test_index_references_existing_static_assets(self):
        index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="/static/style.css"', index_html)
        self.assertIn('src="/static/app.js"', index_html)
        self.assertTrue((STATIC_DIR / "style.css").is_file())
        self.assertTrue((STATIC_DIR / "app.js").is_file())

    def test_map_nodes_expose_ids_for_connection_drawing(self):
        app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("setAttribute('data-node-id', String(node.id))", app_js)
        self.assertIn("getAttribute('data-node-id')", app_js)
        self.assertIn("drawMapConnections(sess.map_nodes, sess.available_node_ids)", app_js)

    def test_javascript_syntax_passes_node_check(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")

        result = subprocess.run(
            ["node", "--check", str(STATIC_DIR / "app.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
