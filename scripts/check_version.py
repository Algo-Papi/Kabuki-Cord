from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Kabuki-Cord version metadata.")
    parser.add_argument(
        "--tag",
        default="",
        help="Release tag to compare against pyproject.toml, for example v1.0.39.",
    )
    parser.add_argument(
        "--check-github-ref",
        action="store_true",
        help="When running in GitHub Actions, compare tag refs against pyproject.toml.",
    )
    parser.add_argument(
        "--print-latest-tag",
        action="store_true",
        help="Print the latest local git tag for release hygiene diagnostics.",
    )
    args = parser.parse_args()

    version = project_version()
    expected_tag = f"v{version}"
    print(f"pyproject version: {version}")
    print(f"expected release tag: {expected_tag}")

    latest_tag = latest_git_tag()
    if args.print_latest_tag:
        print(f"latest local git tag: {latest_tag or '(none)'}")

    tag = args.tag.strip()
    if args.check_github_ref and not tag:
        ref_type = os.getenv("GITHUB_REF_TYPE", "")
        ref_name = os.getenv("GITHUB_REF_NAME", "")
        ref = os.getenv("GITHUB_REF", "")
        if ref_type == "tag" or ref.startswith("refs/tags/"):
            tag = ref_name or ref.rsplit("/", 1)[-1]

    if tag:
        if tag != expected_tag:
            print(
                f"Version mismatch: tag {tag!r} does not match pyproject version {version!r}.",
                file=sys.stderr,
            )
            return 1
        print("tag matches pyproject version.")
    elif latest_tag and latest_tag != expected_tag and not is_development_version(version):
        print(
            "release hygiene warning: latest local tag does not match pyproject version "
            f"({latest_tag} != {expected_tag}). Cut a release tag or mark the version as dev."
        )
    elif is_development_version(version):
        print("development version; no matching release tag is expected.")

    return 0


def project_version() -> str:
    payload = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = str(payload.get("project", {}).get("version", "")).strip()
    if not version:
        raise SystemExit("pyproject.toml is missing [project].version")
    return version


def is_development_version(version: str) -> bool:
    return any(marker in version.lower() for marker in (".dev", "+dev"))


def latest_git_tag() -> str:
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-creatordate"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


if __name__ == "__main__":
    sys.exit(main())
