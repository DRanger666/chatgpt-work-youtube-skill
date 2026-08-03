#!/usr/bin/env python3

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path


CREDENTIAL_PATH = Path(
    "/workspace/.chatgpt-work-credentials/youtube/youtube-workbench-secrets.env"
)
CREDENTIAL_NAMES = ("GEMINI_API_KEY", "GEMINI_API_KEY_FALLBACK")


class CredentialError(Exception):
    pass


def parse_credentials(text):
    if not isinstance(text, str):
        raise CredentialError("Credential input must be UTF-8 text")

    values = {}
    for line in text.splitlines():
        if not line or line.count("=") != 1:
            raise CredentialError("Credential input contains a malformed line")
        name, value = line.split("=", 1)
        if name not in CREDENTIAL_NAMES:
            raise CredentialError("Credential input contains an unexpected assignment")
        if name in values:
            raise CredentialError(f"Credential input repeats {name}")
        if not value:
            raise CredentialError(f"Credential input has an empty {name}")
        values[name] = value

    missing = [name for name in CREDENTIAL_NAMES if name not in values]
    if missing:
        raise CredentialError(f"Credential input is missing {missing[0]}")
    if values[CREDENTIAL_NAMES[0]] == values[CREDENTIAL_NAMES[1]]:
        raise CredentialError("Primary and fallback Gemini credentials must differ")
    return values


def normalized_text(values):
    return "".join(f"{name}={values[name]}\n" for name in CREDENTIAL_NAMES)


def _require_directory(path):
    try:
        details = path.lstat()
    except FileNotFoundError as error:
        raise CredentialError("Gemini credential directory is missing") from error
    if not stat.S_ISDIR(details.st_mode) or path.is_symlink():
        raise CredentialError("Gemini credential directory is not a real directory")
    if stat.S_IMODE(details.st_mode) != 0o700:
        raise CredentialError("Gemini credential directory must have mode 0700")


def load_credentials():
    path = CREDENTIAL_PATH
    _require_directory(path.parent)
    try:
        details = path.lstat()
    except FileNotFoundError as error:
        raise CredentialError("Gemini credential file is missing") from error
    if not stat.S_ISREG(details.st_mode) or path.is_symlink():
        raise CredentialError("Gemini credential path is not a regular file")
    if stat.S_IMODE(details.st_mode) != 0o600:
        raise CredentialError("Gemini credential file must have mode 0600")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise CredentialError("Gemini credential file is not valid UTF-8") from error
    values = parse_credentials(text)
    if text != normalized_text(values):
        raise CredentialError("Gemini credential file is not normalized")
    return values


def _prepare_directory(directory):
    root = directory.parent
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise CredentialError("Credential storage root is not a real directory")
    os.chmod(root, 0o700)

    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise CredentialError("Gemini credential directory is not a real directory")
    os.chmod(directory, 0o700)


def install_credentials(text):
    path = CREDENTIAL_PATH
    values = parse_credentials(text)
    content = normalized_text(values)
    _prepare_directory(path.parent)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    load_credentials()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Install or check the protected local Gemini credential file"
    )
    parser.add_argument("operation", choices=("install", "check"))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "install":
            install_credentials(sys.stdin.read())
            print("Gemini credential file installed")
        else:
            load_credentials()
            print("Gemini credential file is valid")
    except CredentialError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
