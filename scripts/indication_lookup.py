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
    python indication_lookup.py --report-date "21 October 2019" --had exome --singleton
    python indication_lookup.py --list
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parent.parent / "assets" / "indication_index.json"

# "no developmental delay" contains "developmental delay". A plain substring test
# reads a parent ruling a feature OUT as evidence that it is present, and routes
# the contested no-delay picture into the indication that looks clearly eligible.
NEGATOR = re.compile(
    r"\b(?:no|not|without|denie[sd]|absent|negative\s+for|free\s+of|ruled\s+out|never)\b",
    re.IGNORECASE,
)

# Negation belongs to its own clause. A fixed character window gets this wrong in
# both directions at once: too short and "autism without any significant
# developmental delay" reads as delay being present; too long and "no seizures,
# global developmental delay" reads the delay as negated too. Bounding the scan
# at the nearest clause break fixes both, because negation does not cross one.
# `with` breaks a clause; `without` must not, so it is excluded by lookahead.
CLAUSE_BREAK = re.compile(r"[,;:.()\n]|\band\b|\bbut\b|\bwith\b(?!out)", re.IGNORECASE)


def mentions(term: str, text: str) -> bool:
    """Whether `term` appears in `text` other than under a negation."""
    for m in re.finditer(re.escape(term.lower()), text):
        prefix = text[:m.start()]
        clause_start = max((b.end() for b in CLAUSE_BREAK.finditer(prefix)), default=0)
        if not NEGATOR.search(prefix[clause_start:]):
            return True
    return False

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


def match_indications(index: dict, features: str) -> list[tuple[str, dict, list[str], bool]]:
    """
    Match free-text clinical features against curated trigger groups.

    Every group must contribute at least one hit. A single flat trigger list let
    the word "autism" alone match the *with developmental delay* indication —
    routing a picture that may not qualify straight into "testing is indicated",
    which is the overpromise this skill exists to avoid.

    `absent_triggers` excludes an indication when a contradicting feature is
    present. An indication matched partly on absence is returned with a flag,
    because absence of a phrase is not evidence that the feature is absent.

    Returns (key, entry, which triggers matched, matched_via_absence).
    """
    text = features.lower()
    hits = []
    for key, entry in index["indications"].items():
        groups = entry.get("trigger_groups") or []
        if not groups:
            continue

        matched: list[str] = []
        for group in groups:
            group_hits = [t for t in group if mentions(t, text)]
            if not group_hits:
                matched = []
                break
            matched.extend(group_hits)
        if not matched:
            continue

        absent = entry.get("absent_triggers") or []
        if any(mentions(t, text) for t in absent):
            continue

        hits.append((key, entry, matched, bool(absent)))

    # More trigger hits means a better-evidenced match; show those first.
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


def render_indication(index: dict, key: str, entry: dict, matched: list[str],
                      via_absence: bool = False, brief: bool = False) -> str:
    out = [f"## {entry['label']}"]
    if matched:
        out.append(f"_(matched on: {', '.join(sorted(set(matched)))})_")
    if via_absence:
        out.append("")
        out.append("  ! MATCHED PARTLY ON ABSENCE. Nothing in what you were told mentioned")
        out.append("    developmental delay or intellectual disability — but not being")
        out.append("    mentioned is not the same as not being present. Ask before relying")
        out.append("    on this: it decides which indication applies, and they differ.")
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
    if brief:
        # Named here, detailed once at the end — only worth it when more than
        # one indication matched, or the summary costs more than it saves.
        out += [f"  - {index['authorities'].get(a, {}).get('name', a)}"
                for a in entry.get("authorities", [])]
    else:
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


# Report dates arrive in whichever form the report used; parse_report.py emits
# them verbatim. Only the year is relied on for elapsed time — a day/month
# ambiguity in 03/04/2019 cannot move the answer by more than a few months, and
# pretending to a precision the format does not carry would be worse.
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_report_year(text: str) -> tuple[int | None, int | None, bool]:
    """Return (year, month, ambiguous_day_month) from a report-date string."""
    t = text.strip().lower()
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}$", t)
    if m:
        return int(m.group(1)), int(m.group(2)), False
    m = re.match(r"^(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})$", t)
    if m:
        return int(m.group(3)), _MONTHS.get(m.group(2)), False
    m = re.match(r"^([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$", t)
    if m:
        return int(m.group(3)), _MONTHS.get(m.group(1)), False
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", t)
    if m:
        year = int(m.group(3))
        year += 2000 if year < 100 else 0
        a, b = int(m.group(1)), int(m.group(2))
        # Ambiguous only when both halves could be a month.
        return year, (b if a > 12 else None), a <= 12 and b <= 12
    m = re.search(r"\b((?:19|20)\d{2})\b", t)
    if m:
        return int(m.group(1)), None, False
    return None, None, False


def render_reanalysis(index: dict, report_date: str, had: list[str],
                      today_year: int, singleton: bool | None) -> str:
    """
    The case-level reanalysis picture: elapsed time, whether there is anything to
    reanalyse, and what the prior assay left uncovered.

    Deliberately says nothing about which genes were described since. That needs
    a time-indexed discovery list this tool does not hold and must not invent —
    and the argument does not depend on it. "A 2019 singleton exome, reanalysed
    against current knowledge" is a complete request without naming a gene.
    """
    year, month, ambiguous = parse_report_year(report_date)
    out = ["## Reanalysis assessment", ""]

    if not year:
        out.append(f"  Could not read a year from '{report_date}'. Elapsed time is the")
        out.append("  whole argument here — establish the report date before proceeding.")
        out.append("")
        return "\n".join(out)

    elapsed = today_year - year
    out.append(f"  Report year: {year}   Elapsed: ~{elapsed} year(s)")
    if ambiguous:
        out.append("  (day/month order ambiguous in this format — year is what is relied on)")
    out.append("")

    if elapsed >= 2:
        out.append("  Old enough that reanalysis is reasonable to raise. Nobody recalls")
        out.append("  these families proactively; no system has that mechanism.")
    else:
        out.append("  Recent. Do NOT recommend reanalysis — it wastes a request and")
        out.append("  undermines the rest of the ask.")
    out.append("")

    if not had:
        out.append("  No prior assay given. Which test was done decides whether reanalysis")
        out.append("  is even the right request — ask.")
        out.append("")
        return "\n".join(out)

    out.append("### Is there anything to reanalyse?")
    for key in had:
        g = index["test_gaps"].get(key)
        if not g:
            out.append(f"  - {key}: not a curated test type")
            continue
        verdict = "YES" if g.get("reanalysable") else "NO"
        out.append(f"  - {g['label']}: {verdict} — {g.get('reanalysis_note','')}")
    out.append("")

    if singleton is True:
        out.append("### Family structure")
        out.append("  Singleton. Adding parental samples is a distinct and often stronger")
        out.append("  ask than reanalysis alone — it can resolve variants the original")
        out.append("  analysis had to leave uncertain. Name it as its own option.")
        out.append("")
    elif singleton is False:
        out.append("### Family structure")
        out.append("  Trio already. Reanalysis is re-examination against current knowledge,")
        out.append("  not a change in family structure.")
        out.append("")

    out.append("### What this assessment does NOT establish")
    out.append("  Which genes have been described since. That needs a time-indexed")
    out.append("  discovery list this tool does not hold, and must not be recited from")
    out.append("  memory. The request does not need it: the case-level facts above —")
    out.append("  date, assay, coverage, family structure — are the argument.")
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
    ap.add_argument("--report-date",
                    help="Date on the prior report — enables the reanalysis assessment")
    ap.add_argument("--singleton", action="store_true", help="Prior test was proband-only")
    ap.add_argument("--trio", action="store_true", help="Prior test included both parents")
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

    if not args.features and not args.had and not args.report_date:
        ap.error("provide --features, --had, --report-date, or --list")
        return 2
    if args.singleton and args.trio:
        ap.error("--singleton and --trio are mutually exclusive")
        return 2
    singleton = True if args.singleton else False if args.trio else None

    hits = match_indications(index, args.features) if args.features else []

    if args.json:
        print(json.dumps({
            "indications": {k: v for k, v, _, _ in hits},
            "matched_triggers": {k: sorted(set(m)) for k, _, m, _ in hits},
            "matched_via_absence": [k for k, _, _, a in hits if a],
            "test_gaps": {k: index["test_gaps"][k] for k in args.had if k in index["test_gaps"]},
        }, indent=2))
        return 0

    if args.features:
        if hits:
            brief = len(hits) > 1
            for key, entry, matched, via_absence in hits:
                print(render_indication(index, key, entry, matched, via_absence, brief))
            # Each authority once, however many indications cite it — the block
            # for the test directory alone ran to four repeats in one call.
            cited: list[str] = []
            if brief:
                for _k, entry, _m, _a in hits:
                    for a in entry.get("authorities", []):
                        if a not in cited:
                            cited.append(a)
            if cited:
                print("## Authorities — fetch these")
                for a in cited:
                    print("\n".join(render_authority(index, a)))
                print()
        else:
            print(f"No curated indication matched: {args.features}\n")
            print(NO_MATCH_GUIDANCE)
            print()

    if args.report_date:
        print(render_reanalysis(index, args.report_date, args.had,
                                date.today().year, singleton))

    for had in args.had:
        print(render_gap(index, had))

    print("Reminder: this routes to the authority. It does not establish eligibility,")
    print("and it carries no criteria, thresholds, or yield figures by design. Retrieve")
    print("them and cite with a retrieval date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
