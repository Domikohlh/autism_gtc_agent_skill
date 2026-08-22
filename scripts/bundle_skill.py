#!/usr/bin/env python3
"""
Build an upload-ready skill folder from this repository.

The repository is a development workspace: it carries a test corpus, diagrams, a
long README, git history and Python caches. None of that belongs in an uploaded
skill, and trimming it by hand before every upload is how a stale copy of one
file eventually ships.

This produces `dist/<skill-name>/` containing only what the skill needs, then
CHECKS the result rather than trusting the copy:

  - the frontmatter is within the platform's name and description limits
  - nothing the skill points at is missing from the bundle
  - every script still runs, with its assets resolvable from its new location

A bundle that fails a check is still written, so you can look at it, but the exit
code is non-zero and the reason is printed. Silence would be the worse failure:
an upload that is quietly missing a reference file behaves like a skill with a
gap in its judgement, not like a broken build.

Usage:
    python scripts/bundle_skill.py
    python scripts/bundle_skill.py --out /tmp/upload   # somewhere else
    python scripts/bundle_skill.py --zip               # also write a .zip
    python scripts/bundle_skill.py --list              # show what would be copied
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What an uploaded skill needs. Everything else is development material.
#
# README.md is deliberately absent: it documents the repository — tests,
# fixtures, roadmap, licence rationale — none of which exists in a bundle, so
# shipping it would put dangling references in front of the agent. The privacy
# content the skill actually relies on lives in references/data_privacy.md.
INCLUDE_FILES = ["SKILL.md", "LICENSE", "LICENSE-DOCS", "NOTICE"]
INCLUDE_DIRS = ["references", "scripts", "assets"]

# Skipped inside the directories above.
SKIP_NAMES = {"__pycache__", ".DS_Store", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_FILES = {"bundle_skill.py"}  # a build tool, not part of the skill

FRONTMATTER_LIMITS = {"name": 64, "description": 1024}


def skill_name() -> str:
    """The bundle directory name, taken from the frontmatter rather than the folder."""
    text = (ROOT / "SKILL.md").read_text()
    m = re.search(r"^name:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else "skill"


def wanted(path: Path) -> bool:
    if path.name in SKIP_NAMES or path.name in SKIP_FILES:
        return False
    if path.suffix in SKIP_SUFFIXES:
        return False
    return not any(part in SKIP_NAMES for part in path.parts)


def collect() -> list[Path]:
    """Repo-relative paths to copy, in a stable order."""
    out: list[Path] = []
    for name in INCLUDE_FILES:
        p = ROOT / name
        if p.is_file():
            out.append(Path(name))
    for name in INCLUDE_DIRS:
        d = ROOT / name
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file() and wanted(f.relative_to(ROOT)):
                out.append(f.relative_to(ROOT))
    return out


def build(dest: Path, files: list[Path]) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)


def sweep(dest: Path) -> None:
    """Remove anything the checks themselves left behind."""
    for d in sorted(dest.rglob("__pycache__"), reverse=True):
        shutil.rmtree(d, ignore_errors=True)
    for f in dest.rglob("*"):
        if f.is_file() and (f.suffix in SKIP_SUFFIXES or f.name in SKIP_NAMES):
            f.unlink()


# --------------------------------------------------------------------------
# Checks on the built bundle
# --------------------------------------------------------------------------

def check_frontmatter(dest: Path) -> list[str]:
    text = (dest / "SKILL.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return ["SKILL.md has no YAML frontmatter block"]

    front, problems = m.group(1), []
    for key, limit in FRONTMATTER_LIMITS.items():
        km = re.search(rf"^{key}:\s*(.*?)(?=\n[a-zA-Z-]+:|\Z)", front, re.S | re.M)
        value = km.group(1).strip() if km else ""
        if not value:
            problems.append(f"frontmatter is missing a non-empty '{key}'")
        elif len(value) > limit:
            problems.append(
                f"{key} is {len(value)} characters, over the {limit} limit by "
                f"{len(value) - limit} — upload will be rejected"
            )
    return problems


def check_references(dest: Path) -> list[str]:
    """
    Every repo path the bundled prose points at must exist in the bundle.

    This is the check that earns the script: a reference file left out of
    INCLUDE_DIRS produces a skill that reads normally and silently loses a whole
    layer of judgement.
    """
    pattern = re.compile(r"\b(?:references|scripts|assets|docs|tests)/[A-Za-z0-9_./-]+")
    problems = []
    for f in sorted(dest.rglob("*.md")):
        for m in pattern.finditer(f.read_text()):
            ref = m.group(0).rstrip(".,;:)`")
            if not (dest / ref).exists():
                problems.append(f"{f.relative_to(dest)} points at missing {ref}")
    return sorted(set(problems))


def check_scripts_run(dest: Path) -> list[str]:
    """Each script must run from its new location and find its assets."""
    probes = [
        ("gene_lookup.py", ["PTEN"]),
        ("indication_lookup.py", ["--list"]),
        ("plain_language.py", ["--text", "de novo pathogenic variant"]),
        ("parse_report.py", ["--text", "PTEN NM_000314.8:c.388C>T Pathogenic"]),
        ("render_brief.py", ["--help"]),
    ]
    problems = []
    for name, args in probes:
        script = dest / "scripts" / name
        if not script.is_file():
            problems.append(f"scripts/{name} is missing from the bundle")
            continue
        # -B: running the probes would otherwise write __pycache__ into the
        # bundle being verified, so the check would dirty its own result.
        r = subprocess.run([sys.executable, "-B", str(script), *args],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            first = (r.stderr.strip().splitlines() or ["no stderr"])[-1]
            problems.append(f"scripts/{name} exited {r.returncode}: {first}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"),
                    help="Directory to build into (default: dist/)")
    ap.add_argument("--zip", action="store_true", help="Also write <name>.zip beside it")
    ap.add_argument("--list", action="store_true",
                    help="Print what would be copied and stop")
    args = ap.parse_args()

    files = collect()
    if args.list:
        for rel in files:
            print(f"  {rel}")
        print(f"\n{len(files)} files, "
              f"{sum((ROOT / f).stat().st_size for f in files):,} bytes")
        return 0

    dest = Path(args.out).expanduser().resolve() / skill_name()
    build(dest, files)
    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"built {dest}")
    print(f"  {len(files)} files, {total:,} bytes")

    problems = (check_frontmatter(dest)
                + check_references(dest)
                + check_scripts_run(dest))
    sweep(dest)
    if problems:
        print("\nProblems — fix these before uploading:")
        for p in problems:
            print(f"  FAIL  {p}")
        return 1
    print("  frontmatter within limits · references resolve · scripts run")

    if args.zip:
        archive = dest.parent / f"{dest.name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(dest.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(dest.parent))
        print(f"  wrote {archive} ({archive.stat().st_size:,} bytes)")

    print(f"\nUpload this folder: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
