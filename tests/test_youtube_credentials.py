import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import youtube_credentials


PRIMARY = "test-primary-value"
FALLBACK = "test-fallback-value"
VALID_TEXT = (
    f"GEMINI_API_KEY={PRIMARY}\n"
    f"GEMINI_API_KEY_FALLBACK={FALLBACK}\n"
)


class YouTubeCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = (
            Path(self.temporary.name)
            / ".chatgpt-work-credentials"
            / "youtube"
            / "youtube-workbench-secrets.env"
        )
        self.path_patch = mock.patch.object(
            youtube_credentials,
            "CREDENTIAL_PATH",
            self.path,
        )
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_input_is_normalized_in_fixed_order(self):
        values = youtube_credentials.parse_credentials(
            f"GEMINI_API_KEY_FALLBACK={FALLBACK}\n"
            f"GEMINI_API_KEY={PRIMARY}\n"
        )
        self.assertEqual(
            youtube_credentials.normalized_text(values),
            VALID_TEXT,
        )

    def test_rejects_missing_duplicate_unexpected_identical_and_malformed_input(self):
        cases = {
            "missing": f"GEMINI_API_KEY={PRIMARY}\n",
            "duplicate": (
                f"GEMINI_API_KEY={PRIMARY}\n"
                f"GEMINI_API_KEY={PRIMARY}\n"
                f"GEMINI_API_KEY_FALLBACK={FALLBACK}\n"
            ),
            "unexpected": (
                f"GEMINI_API_KEY={PRIMARY}\n"
                f"GEMINI_API_KEY_FALLBACK={FALLBACK}\n"
                "OTHER=value\n"
            ),
            "identical": (
                f"GEMINI_API_KEY={PRIMARY}\n"
                f"GEMINI_API_KEY_FALLBACK={PRIMARY}\n"
            ),
            "empty": (
                "GEMINI_API_KEY=\n"
                f"GEMINI_API_KEY_FALLBACK={FALLBACK}\n"
            ),
            "malformed": (
                f"GEMINI_API_KEY={PRIMARY}\n"
                "not-an-assignment\n"
                f"GEMINI_API_KEY_FALLBACK={FALLBACK}\n"
            ),
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(youtube_credentials.CredentialError):
                    youtube_credentials.parse_credentials(text)

    def test_install_uses_atomic_replace_and_protected_permissions(self):
        with mock.patch.object(
            youtube_credentials.os,
            "replace",
            wraps=os.replace,
        ) as replace:
            youtube_credentials.install_credentials(VALID_TEXT)

        replace.assert_called_once()
        self.assertEqual(self.path.read_text(encoding="utf-8"), VALID_TEXT)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(
            youtube_credentials.load_credentials(),
            {
                "GEMINI_API_KEY": PRIMARY,
                "GEMINI_API_KEY_FALLBACK": FALLBACK,
            },
        )
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*")), [])

    def test_invalid_install_preserves_existing_file(self):
        youtube_credentials.install_credentials(VALID_TEXT)
        before = self.path.read_bytes()
        with self.assertRaises(youtube_credentials.CredentialError):
            youtube_credentials.install_credentials(f"GEMINI_API_KEY={PRIMARY}\n")
        self.assertEqual(self.path.read_bytes(), before)

    def test_check_rejects_directory_and_file_permission_changes(self):
        youtube_credentials.install_credentials(VALID_TEXT)
        os.chmod(self.path, 0o644)
        with self.assertRaisesRegex(
            youtube_credentials.CredentialError,
            "0600",
        ):
            youtube_credentials.load_credentials()

        os.chmod(self.path, 0o600)
        os.chmod(self.path.parent, 0o755)
        with self.assertRaisesRegex(
            youtube_credentials.CredentialError,
            "0700",
        ):
            youtube_credentials.load_credentials()

    def test_cli_output_never_contains_credential_values(self):
        output = io.StringIO()
        errors = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(VALID_TEXT)), contextlib.redirect_stdout(
            output
        ), contextlib.redirect_stderr(errors):
            self.assertEqual(youtube_credentials.main(["install"]), 0)
            self.assertEqual(youtube_credentials.main(["check"]), 0)

        rendered = output.getvalue() + errors.getvalue()
        self.assertNotIn(PRIMARY, rendered)
        self.assertNotIn(FALLBACK, rendered)

        output = io.StringIO()
        errors = io.StringIO()
        rejected = VALID_TEXT + "OTHER=must-not-appear\n"
        with mock.patch("sys.stdin", io.StringIO(rejected)), contextlib.redirect_stdout(
            output
        ), contextlib.redirect_stderr(errors):
            self.assertEqual(youtube_credentials.main(["install"]), 1)
        rendered = output.getvalue() + errors.getvalue()
        self.assertNotIn("must-not-appear", rendered)


if __name__ == "__main__":
    unittest.main()
