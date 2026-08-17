#!/usr/bin/env python3
"""
Translate report vocabulary into words a family can use.

Scans technical text — a report's interpretation paragraph, a clinic letter, a
draft a clinician is about to hand over — and returns, for every term it finds,
the plain rendering that carries the same meaning, plus the traps where a
careless translation would change it.

It rewrites nothing. Substituting phrases mechanically produces sentences no
person would write, and the terms that matter most are exactly the ones where
the surrounding sentence has to change too. This surfaces the vocabulary and the
hazards; the writing is yours.

Usage:
    python plain_language.py --text "de novo pathogenic variant, heterozygous"
    python plain_language.py report.txt
    python plain_language.py report.txt --json
    python plain_language.py --list
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "assets" / "plain_language.json"


def load_glossary() -> dict:
    if not GLOSSARY_PATH.exists():
        print(f"error: glossary not found at {GLOSSARY_PATH}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(GLOSSARY_PATH.read_text())


def find_terms(glossary: dict, text: str) -> list[tuple[str, dict]]:
    """
    Terms present in `text`, longest first.

    Longest-first matters: "likely pathogenic" and "pathogenic" are different
    classifications, and reporting the shorter one for text that says the longer
    would promote the finding a level. Once the longer phrase is matched, the
    span is consumed so the shorter cannot also claim it.
    """
    lowered = text.lower()
    claimed: list[tuple[int, int]] = []
    found: list[tuple[str, dict]] = []

    for term in sorted(glossary["terms"], key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(term.lower())}\b", lowered):
            if any(s <= m.start() < e for s, e in claimed):
                continue
            claimed.append((m.start(), m.end()))
            found.append((term, glossary["terms"][term]))
            break
    return sorted(found, key=lambda f: lowered.index(f[0].lower()))


def render(glossary: dict, found: list[tuple[str, dict]], text: str) -> str:
    out: list[str] = []
    if not found:
        out.append("No glossary terms found. Either the text is already plain, or it uses")
        out.append("vocabulary this glossary has not curated — read it yourself and apply")
        out.append("the register discipline in references/output_templates.md.")
        return "\n".join(out)

    out.append(f"## {len(found)} term(s) to translate")
    out.append("")
    out.append(f"  {glossary['_meta']['the_rule']}")
    out.append("")

    careful = []
    for term, entry in found:
        out.append(f"### {term}")
        out.append(f"  WRITE: {entry['plain']}")
        if entry.get("keep"):
            out.append("  KEEP THE WORD TOO — they will see it on paperwork and need to")
            out.append("  recognise it. Explain it once, then use the plain phrasing.")
        if entry.get("careful"):
            out.append(f"  ! {entry['careful']}")
            careful.append(term)
        out.append("")

    out.append("## Always keep, whatever else is simplified")
    for k, why in glossary["always_keep"].items():
        out.append(f"  - {k}: {why}")
    out.append("")

    if careful:
        out.append("## Do not translate these carelessly")
        out.append(f"  {', '.join(careful)} — each carries a trap noted above. A translation")
        out.append("  that loses the uncertainty, or promotes a classification a level, is")
        out.append("  worse than leaving the term in.")
        out.append("")

    out.append("Rewrite the sentences; do not substitute phrases into them. Then check the")
    out.append("result against the register discipline in references/output_templates.md.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", nargs="?", help="File of technical text to scan")
    ap.add_argument("--text", help="Scan a literal string instead of a file")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON")
    ap.add_argument("--list", action="store_true", help="List the whole glossary")
    args = ap.parse_args()

    glossary = load_glossary()

    if args.list:
        for term, entry in sorted(glossary["terms"].items()):
            flag = " [keep]" if entry.get("keep") else ""
            trap = " [trap]" if entry.get("careful") else ""
            print(f"  {term}{flag}{trap}\n      {entry['plain']}")
        return 0

    if args.text:
        text = args.text
    elif args.path:
        p = Path(args.path)
        if not p.exists():
            print(f"error: {p} not found", file=sys.stderr)
            return 1
        text = p.read_text(errors="replace")
    else:
        ap.error("provide a file path, --text, or --list")
        return 2

    found = find_terms(glossary, text)
    if args.json:
        print(json.dumps({
            "terms": [{"term": t, **e} for t, e in found],
            "always_keep": glossary["always_keep"],
        }, indent=2))
        return 0

    print(render(glossary, found, text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
