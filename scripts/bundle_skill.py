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
SKILL_BODY_GUIDANCE = 500

# The value after "key: " in this frontmatter is a YAML *plain scalar* — unquoted
# — and a handful of characters silently change what it means. A colon followed
# by whitespace is the one that bites: "care implications: surveillance" parses
# as a nested mapping and the import fails with an error that names a column
# rather than a cause. Length checks alone let that ship once already.
YAML_INDICATORS = "-?:,[]{}#&*!|>'\"%@`"


def yaml_scalar_problems(key: str, value: str) -> list[str]:
    """Characters that break an unquoted YAML scalar. Stdlib only, always runs."""
    problems = []
    if re.search(r":\s", value) or value.endswith(":"):
        problems.append(
            f"{key} contains a colon followed by whitespace. YAML reads that as a "
            "nested mapping and the skill will fail to import — reword to drop the colon"
        )
    if " #" in value:
        problems.append(f"{key} contains ' #', which YAML reads as the start of a comment")
    if value[:1] and value[0] in YAML_INDICATORS:
        problems.append(f"{key} starts with {value[0]!r}, a YAML indicator character")
    if "\t" in value:
        problems.append(f"{key} contains a tab character, which YAML does not allow here")
    return problems


def yaml_parse_problems(front: str) -> list[str]:
    """
    A real parse, when PyYAML happens to be importable.

    Optional on purpose: this repository has no dependencies, so the lint above
    is the guaranteed check and this is the stronger one when it is available.
    """
    try:
        import yaml  # noqa: PLC0415 - optional, absence is not an error
    except ImportError:
        return []
    try:
        data = yaml.safe_load(front)
    except Exception as exc:  # yaml.YAMLError, but never let the check itself crash
        return [f"frontmatter is not valid YAML — {str(exc).splitlines()[0]}"]
    if not isinstance(data, dict):
        return ["frontmatter does not parse to a mapping of fields"]
    return []


def validate_frontmatter(skill_md: Path) -> tuple[list[str], list[str]]:
    """
    (failures, warnings) for a SKILL.md. The single implementation, used by this
    script against a built bundle and by the test suite against the repository.
    """
    text = skill_md.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return ["SKILL.md has no YAML frontmatter block"], []

    front, body = m.group(1), m.group(2)
    failures = list(yaml_parse_problems(front))
    warnings: list[str] = []

    for key, limit in FRONTMATTER_LIMITS.items():
        km = re.search(rf"^{key}:\s*(.*?)(?=\n[a-zA-Z-]+:|\Z)", front, re.S | re.M)
        value = km.group(1).strip() if km else ""
        if not value:
            failures.append(f"frontmatter is missing a non-empty '{key}'")
            continue
        if len(value) > limit:
            failures.append(
                f"{key} is {len(value)} characters, over the {limit} limit by "
                f"{len(value) - limit} — upload will be rejected"
            )
        if "<" in value or ">" in value:
            failures.append(f"{key} contains an angle bracket; XML tags are rejected")
        failures.extend(yaml_scalar_problems(key, value))

    name_m = re.search(r"^name:\s*(.+)$", front, re.M)
    name = name_m.group(1).strip() if name_m else ""
    if name and not re.fullmatch(r"[a-z0-9-]+", name):
        failures.append(f"name {name!r} must be lowercase letters, numbers and hyphens only")
    if re.search(r"anthropic|claude", name, re.I):
        failures.append(f"name {name!r} contains a reserved word")

    lines = len(body.splitlines())
    if lines > SKILL_BODY_GUIDANCE:
        warnings.append(
            f"SKILL.md body is {lines} lines; the guidance is under {SKILL_BODY_GUIDANCE}. "
            "Not an upload blocker — move detail into references/"
        )
    return failures, warnings


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
    return validate_frontmatter(dest / "SKILL.md")[0]


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


# Anthropic's documented ceiling for a custom skill upload, uncompressed.
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

# Written into every archive entry so the same tree always produces the same
# bytes. Real mtimes make two identical bundles differ, which turns "did this
# change?" into a question you cannot answer by looking.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def write_zip(dest: Path, flat: bool = False) -> Path:
    """
    Zip the built bundle.

    `SKILL.md` must sit at the upload root or at the top of a single enclosing
    folder. The default writes the enclosing folder, which is the form the docs
    show; `flat` writes the files at the archive root for uploaders that want
    that instead.

    Built with zipfile rather than the Finder's Compress, deliberately: macOS
    adds a `__MACOSX/` tree and `.DS_Store` entries that some uploaders reject
    and none of them need.
    """
    archive = dest.parent / f"{dest.name}.zip"
    files = sorted(f for f in dest.rglob("*") if f.is_file())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            rel = f.relative_to(dest if flat else dest.parent)
            info = zipfile.ZipInfo(rel.as_posix(), date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            # Executable only where there is a shebang to honour.
            executable = f.read_bytes()[:2] == b"#!"
            info.external_attr = (0o755 if executable else 0o644) << 16
            z.writestr(info, f.read_bytes())
    return archive


def check_archive(archive: Path, flat: bool) -> list[str]:
    """The archive must be readable, correctly shaped, and free of junk."""
    problems = []
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad is not None:
            return [f"archive is corrupt at {bad}"]

        names = z.namelist()
        expected = "SKILL.md" if flat else f"{archive.stem}/SKILL.md"
        if expected not in names:
            problems.append(
                f"{expected} is not in the archive — an uploader looks for SKILL.md at "
                "the root or at the top of a single enclosing folder"
            )
        junk = [n for n in names
                if n.startswith("__MACOSX/") or Path(n).name in SKIP_NAMES
                or Path(n).suffix in SKIP_SUFFIXES]
        if junk:
            problems.append(f"archive contains {len(junk)} junk entries, first {junk[0]}")

        if not flat:
            roots = {n.split("/", 1)[0] for n in names}
            if len(roots) > 1:
                problems.append(f"archive has {len(roots)} top-level entries, expected one folder")

        raw = sum(i.file_size for i in z.infolist())
        if raw > MAX_UPLOAD_BYTES:
            problems.append(
                f"uncompressed contents are {raw:,} bytes, over the "
                f"{MAX_UPLOAD_BYTES:,} upload limit"
            )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"),
                    help="Directory to build into (default: dist/)")
    ap.add_argument("--no-zip", action="store_true",
                    help="Skip the .zip and write only the folder")
    ap.add_argument("--flat", action="store_true",
                    help="Put SKILL.md at the archive root instead of inside a folder")
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

    problems = (check_frontmatter(dest)
                + check_references(dest)
                + check_scripts_run(dest))
    sweep(dest)

    print(f"folder  {dest}")
    print(f"        {len(files)} files, {total:,} bytes")

    archive = None
    if not args.no_zip:
        archive = write_zip(dest, flat=args.flat)
        problems += check_archive(archive, flat=args.flat)
        shape = "SKILL.md at root" if args.flat else f"{dest.name}/SKILL.md"
        print(f"zip     {archive}")
        print(f"        {archive.stat().st_size:,} bytes, {shape}")

    if problems:
        print("\nProblems — fix these before uploading:")
        for p in problems:
            print(f"  FAIL  {p}")
        return 1

    print("        frontmatter valid · references resolve · scripts run"
          + (" · archive verified" if archive else ""))
    print("\nUpload the folder. If your platform rejects a folder upload, "
          "upload the .zip instead.")
    if archive and not args.flat:
        print("If the .zip is also rejected, rebuild with --flat: some uploaders want "
              "SKILL.md\nat the archive root rather than inside a folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
