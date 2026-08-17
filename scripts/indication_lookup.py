#!/usr/bin/env python3
"""
Look up which genetic testing is guideline-indicated for a clinical picture, and
what a test already performed could not have found.

Returns the authorities to FETCH, the tests commonly indicated, and the gaps left
by prior testing. It does NOT return eligibility criteria, age thresholds, or
diagnostic yield figures — those differ between health systems and between
directory versions, and must be read from the cited authority with a retrieval
date. See references/testing_indications.md.

Usage:
    python indication_lookup.py --features "autism, developmental delay"
    python indication_lookup.py --features "epilepsy" --had microarray
    python indication_lookup.py --had microarray --had panel
    python indication_lookup.py --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parent.parent / "assets" / "indication_index.json"

NO_MATCH_GUIDANCE = """\
No curated indication matched those features. That does not mean testing is not
indicated — it means this index has not curated that picture. Do not conclude
either way from silence.

  1. The health system's own criteria — in England, the NHS National Genomic
     Test Directory; elsewhere, the payer or commissioning policy
  2. ACMG 2021 (Manickam et al.) for the paediatric CA/DD/ID recommendation
  3. The clinical genetics service, who decide eligibility in practice

Say plainly which of these you checked and what you found."""


def load_index() -> dict:
    if not INDEX_PATH.exists():
        print(f"error: index not found at {INDEX_PATH}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(INDEX_PATH.read_text())


def match_indications(index: dict, features: str) -> list[tuple[str, dict, list[str]]]:
    """
    Match free-text clinical features against curated triggers.

    Returns (key, entry, which triggers matched) so the caller can show its
    working — a match the user can see is a match they can correct.
    """
    text = features.lower()
    hits = []
    for key, entry in index["indications"].items():
        matched = [t for t in entry.get("triggers", []) if t.lower() in text]
        if matched:
            hits.append((key, entry, matched))
    # Most specific first: more trigger hits means a better-evidenced match.
    hits.sort(key=lambda h: -len(h[2]))
    return hits


def render_authority(index: dict, key: str) -> list[str]:
    a = index["authorities"].get(key)
    if not a:
        return [f"  - {key} (not recorded in the index)"]
    lines = [f"  - {a['name']}"]
    if a.get("body") or a.get("year"):
        lines.append(f"    {a.get('body','')}{', ' + str(a['year']) if a.get('year') else ''}")
    lines.append(f"    Jurisdiction: {a.get('jurisdiction','not recorded')}")
    lines.append(f"    Cite it for: {a.get('establishes','not recorded')}")
    if a.get("url"):
        lines.append(f"    {a['url']}")
    if a.get("find_by"):
        lines.append(f"    FIND BY: {a['find_by']}")
    return lines


def render_indication(index: dict, key: str, entry: dict, matched: list[str]) -> str:
    out = [f"## {entry['label']}"]
    if matched:
        out.append(f"_(matched on: {', '.join(matched)})_")
    out.append("")

    tests = entry.get("commonly_indicated") or []
    out.append("### Tests commonly indicated for this picture")
    if tests:
        out += [f"  - {t}" for t in tests]
        out.append("")
        out.append("  These are the tests usually at issue — NOT a statement that this")
        out.append("  person is eligible. Eligibility is set by the authority below and")
        out.append("  decided by the clinical service. Retrieve it; do not assume it.")
    else:
        out.append("  None recorded as clearly indicated. That is itself the finding —")
        out.append("  say so rather than implying eligibility.")
    out.append("")

    out.append("### Authorities to fetch")
    for a in entry.get("authorities", []):
        out += render_authority(index, a)
    out.append("")

    if entry.get("notes"):
        out.append("### Notes")
        out += [f"  {n}" for n in entry["notes"]]
        out.append("")

    if entry.get("traps"):
        out.append("### Traps — read before writing")
        out += [f"  ! {t}" for t in entry["traps"]]
        out.append("")

    return "\n".join(out)


def render_gap(index: dict, key: str) -> str:
    g = index["test_gaps"].get(key)
    if not g:
        available = ", ".join(sorted(index["test_gaps"]))
        return f"'{key}' is not a curated test type. Known: {available}\n"
    out = [f"## Already done: {g['label']}", ""]
    out.append("### Detects")
    out += [f"  - {d}" for d in g.get("detects", [])]
    out.append("")
    out.append("### Cannot detect — this is the gap")
    out += [f"  - {d}" for d in g.get("cannot_detect", [])]
    out.append("")
    if g.get("note"):
        out.append(f"  {g['note']}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--features", help="Free text: the clinical picture, e.g. 'autism, epilepsy'")
    ap.add_argument("--had", action="append", default=[],
                    help="A test already performed (repeatable): microarray, panel, exome, genome, karyotype, fish, fmr1_repeat")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON")
    ap.add_argument("--list", action="store_true", help="List everything curated")
    args = ap.parse_args()

    index = load_index()

    if args.list:
        print("Indications:")
        for k, v in index["indications"].items():
            print(f"  {k:<34} {v['label']}")
        print("\nTest gaps:")
        for k, v in index["test_gaps"].items():
            print(f"  {k:<34} {v['label']}")
        print("\nAuthorities:")
        for k, v in index["authorities"].items():
            print(f"  {k:<34} {v.get('body','')} — {v.get('jurisdiction','')}")
        return 0

    if not args.features and not args.had:
        ap.error("provide --features, --had, or --list")
        return 2

    hits = match_indications(index, args.features) if args.features else []

    if args.json:
        print(json.dumps({
            "indications": {k: v for k, v, _ in hits},
            "matched_triggers": {k: m for k, _, m in hits},
            "test_gaps": {k: index["test_gaps"][k] for k in args.had if k in index["test_gaps"]},
        }, indent=2))
        return 0

    if args.features:
        if hits:
            for key, entry, matched in hits:
                print(render_indication(index, key, entry, matched))
        else:
            print(f"No curated indication matched: {args.features}\n")
            print(NO_MATCH_GUIDANCE)
            print()

    for had in args.had:
        print(render_gap(index, had))

    print("Reminder: this routes to the authority. It does not establish eligibility,")
    print("and it carries no criteria, thresholds, or yield figures by design. Retrieve")
    print("them and cite with a retrieval date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
