import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "ensure_youtube_mcp.sh"
INSTALL_NAME = "youtube-mcp-portable"
MCP_COMMIT = "06d5e7a83783f7a44498da88ade2ccaa42238747"


class PortableLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def make_install(self):
        install = self.root / INSTALL_NAME
        for relative in (
            "app/dist",
            "runtime/bin",
            "state",
            "work",
        ):
            (install / relative).mkdir(parents=True, exist_ok=True)
        (install / "app/dist/stdio-server.js").write_text("", encoding="utf-8")
        (install / "README.md").write_text("# Test installation\n", encoding="utf-8")
        (install / "VERSION").write_text(
            "\n".join(
                (
                    "installation_name=youtube-mcp-portable",
                    "youtube_mcp_version=1.2.0",
                    f"youtube_mcp_commit={MCP_COMMIT}",
                    "node_version=v24.14.0",
                    "platform=linux-x86_64",
                    "",
                )
            ),
            encoding="utf-8",
        )
        node = install / "runtime/bin/node"
        node.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = --version ]; then\n"
            "  echo v24.14.0\n"
            "else\n"
            "  echo '{\"tools\":[{\"name\":\"research-video\"}]}'\n"
            "fi\n",
            encoding="utf-8",
        )
        node.chmod(0o755)
        return install

    def run_installer(self):
        return subprocess.run(
            [
                "sh",
                str(INSTALLER),
                "--search-root",
                str(self.root),
                "--install-parent",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )

    def test_recognizes_only_the_exact_maintained_layout(self):
        install = self.make_install()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(install))
        self.assertEqual(
            {path.name for path in install.iterdir()},
            {"app", "runtime", "state", "work", "README.md", "VERSION"},
        )

    def test_missing_state_requires_explicit_replacement(self):
        install = self.make_install()
        (install / "state").rmdir()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Replacement required", result.stderr)
        self.assertFalse((install / "state").exists())
        self.assertTrue((install / "work").is_dir())

    def test_unexpected_root_directory_is_not_accepted(self):
        install = self.make_install()
        unexpected = install / "unexpected-root"
        unexpected.mkdir()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Replacement required", result.stderr)
        self.assertTrue(unexpected.is_dir())

    def test_portable_config_directory_is_not_accepted(self):
        install = self.make_install()
        config = install / "config"
        config.mkdir()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Replacement required", result.stderr)
        self.assertTrue(config.is_dir())

    def test_installer_contains_no_root_launcher_or_backup_generation(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn('"$portable/bin/', source)
        self.assertNotIn("${INSTALL_NAME}-invalid-", source)
        self.assertIn('"$portable/state"', source)
        self.assertIn('"$portable/work"', source)


if __name__ == "__main__":
    unittest.main()
