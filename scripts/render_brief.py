#!/usr/bin/env python3
"""
Assemble the two-register output document from a structured findings JSON.

Writes the family-facing section first, a page break, then the clinician-facing
section — so the clinician half can be printed and handed over intact.

The content is yours to write; this script only handles structure, ordering,
de-identification checks, and the closing limits block that must appear in both.

Input JSON shape (all keys optional except `finding_summary`):

{
  "finding_summary": "...",
  "family": {
    "what_was_found": "...",
    "what_this_means": "...",
    "what_this_does_not_mean": "...",
    "tier1_monitoring": "...",
    "tier2_awareness": "...",
    "where_to_find_others": "...",
    "questions": ["...", "..."]
  },
  "clinician": {
    "finding_table": {"Gene": "PTEN", "Classification": "Pathogenic"},
    "gene_disease_association": "...",
    "tier1_surveillance": "...",
    "tier2_associations": "...",
    "management_considerations": "...",
    "secondary_findings": "...",
    "uncertainty": "...",
    "next_steps": "...",
    "sources": [{"text": "...", "url": "...", "retrieved": "2026-08-16"}]
  },
  "urgent": ["Cardiac conduction involvement — prompt cardiology input"]
}

Usage:
    python render_brief.py findings.json --out brief.md
    python render_brief.py findings.json --family-only
"""

from __future__ import annotations


import argparse
import json
import re
import sys
from pathlib import Path

try:
    from phi import find_identifiers
except ImportError:  # imported as a module from outside scripts/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phi import find_identifiers

LIMITS_BLOCK = (
    "> **What this document is and isn't.** This summarises published information "
    "about this genetic finding. It is not medical advice, not a diagnosis, and not "
    "a prediction. Every decision belongs with the clinical team — bring this to them."
)


def check_deidentified(text: str) -> list[str]:
    """
    Identifier shapes still present in the assembled document.

    Uses the same ruleset as the parser (phi.py). This check used to keep its own
    shorter list, which meant a brief carrying a date of birth, a hospital
    number, a lab email and a specimen ID passed untouched — the script writing
    the document handed to a clinic had the weakest check in the repository.
    """
    return find_identifiers(text)


# Advisory checks on the family half only. Testing showed it drifting long,
# technical and tutorial — definitions nobody asked for, citations mid-sentence,
# a teaching voice. These flag the drift; they never block, because a term is
# occasionally the right call and only the writer can tell.
CITATION_SHAPES = [
    # Any parenthetical ending in a year: "(Cage et al., 2024)", "(Brain, 2024)",
    # "(International PHTS Consensus, 2025)". All three are the same drift.
    (re.compile(r"\([^)\n]{3,60},\s*(?:19|20)\d{2}\)"), "parenthetical citation"),
    (re.compile(r"\*[^*\n]{3,60}\*,?\s*\d{4}"), "italicised journal name with a year"),
    (re.compile(r"\b\d{4};\s*\d+\(\d+\)"), "volume/issue citation"),
    (re.compile(r"https?://|\bdoi:", re.IGNORECASE), "URL or DOI"),
    (re.compile(r"\b(?:PMID|GeneReviews|ClinGen|ClinVar|OMIM|ACMG)\b"), "database or body named inline"),
]

# Terms whose fix is deletion, not definition.
JARGON = [
    "haploinsufficiency", "haploinsufficient", "loss-of-function", "gain-of-function",
    "missense", "nonsense variant", "frameshift", "truncating", "penetrance",
    "expressivity", "zygosity", "heterozygous", "homozygous", "hemizygous",
    "allele", "locus", "phenotype", "genotype", "proband", "segregation",
    "in silico", "splice site", "transcript", "HGVS", "copy number variant",
    "mosaicism", "nonsense-mediated decay", "cascade testing", "hypomorphic",
]

FAMILY_WORD_LIMIT = 800


def check_family_register(text: str) -> list[str]:
    """Advisory notes on plainness of the family half. Never blocks."""
    notes = []
    for pattern, label in CITATION_SHAPES:
        if pattern.search(text):
            notes.append(f"{label} in the family half — evidence belongs in the clinician section")
    found = [term for term in JARGON if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)]
    if found:
        notes.append(
            "technical terms in the family half: " + ", ".join(sorted(set(found)))
            + " — replace with what each means in practice rather than defining it"
        )
    words = len(text.split())
    if words > FAMILY_WORD_LIMIT:
        notes.append(
            f"family half is {words} words (target under {FAMILY_WORD_LIMIT}) — a shorter "
            "brief that gets read beats a complete one that does not"
        )
    return notes


def section(title: str, body: str | None, level: int = 2) -> str:
    """Render a section, or nothing at all if the body is empty."""
    if not body or not str(body).strip():
        return ""
    return f"{'#' * level} {title}\n\n{str(body).strip()}"


def assemble(blocks: list[str]) -> str:
    """
    Join complete blocks with exactly one blank line between them.

    Each block is self-contained, so an omitted section leaves no trace — no run
    of blank lines where it would have been, and no heading butted up against
    the block above it, which Markdown would not render as a heading at all.
    """
    return "\n\n".join(b.strip() for b in blocks if b and b.strip()) + "\n"


def quote_block(title: str, items: list[str]) -> str:
    return "\n".join([f"> **{title}**", ">"] + [f"> - {item}" for item in items])


def render_family(data: dict) -> str:
    # `or {}` rather than a default: a key present but null is a normal shape
    # out of a partial pipeline, and should render an empty section, not crash.
    fam = data.get("family") or {}
    out = ["# Understanding this genetic result"]

    summary = data.get("finding_summary")
    if summary and str(summary).strip():
        out.append(f"_{str(summary).strip()}_")

    if data.get("urgent"):
        out.append(quote_block("Please raise these with a doctor promptly:", data["urgent"]))

    out.append(section("What was found", fam.get("what_was_found")))
    out.append(section("What this means", fam.get("what_this_means")))
    out.append(section("What this does not mean", fam.get("what_this_does_not_mean")))
    out.append(section("Health monitoring that goes with this finding", fam.get("tier1_monitoring")))
    out.append(section("Things worth knowing about", fam.get("tier2_awareness")))
    out.append(section("Where to find others", fam.get("where_to_find_others")))

    questions = fam.get("questions") or []
    if questions:
        out.append(
            "## Questions to bring to your next appointment\n\n"
            + "\n".join(f"- {q}" for q in questions)
        )

    out.append(LIMITS_BLOCK)
    return assemble(out)


def render_clinician(data: dict) -> str:
    clin = data.get("clinician") or {}
    out = ["# Genomic result summary — clinician section"]

    summary = data.get("finding_summary")
    if summary and str(summary).strip():
        out.append(f"_{str(summary).strip()}_")

    if data.get("urgent"):
        out.append(quote_block("Time-critical:", data["urgent"]))

    table = clin.get("finding_table") or {}
    if table:
        rows = "\n".join(
            f"| {k} | {v if v not in (None, '') else '—'} |" for k, v in table.items()
        )
        out.append("## Finding\n\n| Field | Value |\n|---|---|\n" + rows)

    out.append(section("Gene–disease association", clin.get("gene_disease_association")))
    out.append(section("Established surveillance — Tier 1", clin.get("tier1_surveillance")))
    out.append(section("Documented associations without formal protocol — Tier 2", clin.get("tier2_associations")))
    out.append(section("Management considerations", clin.get("management_considerations")))
    out.append(section("Secondary findings", clin.get("secondary_findings")))
    out.append(section("Uncertainty and limitations", clin.get("uncertainty")))
    out.append(section("Suggested next steps", clin.get("next_steps")))

    sources = clin.get("sources") or []
    if sources:
        lines = []
        for i, s in enumerate(sources, 1):
            line = f"{i}. {s.get('text', '')}"
            if s.get("url"):
                line += f" — {s['url']}"
            if s.get("retrieved"):
                line += f" _(retrieved {s['retrieved']})_"
            lines.append(line)
        out.append("## Sources\n\n" + "\n".join(lines))
    else:
        out.append(
            "## Sources\n\n_No sources recorded. This is a problem — every clinical "
            "assertion above needs a source and a retrieval date._"
        )

    out.append(LIMITS_BLOCK)
    return assemble(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("findings", help="Structured findings JSON")
    ap.add_argument("--out", help="Write to this path (default: stdout)")
    ap.add_argument("--family-only", action="store_true")
    ap.add_argument("--clinician-only", action="store_true")
    ap.add_argument(
        "--allow-phi", action="store_true",
        help="Write the file even if the PHI check finds identifiers (it will not by default)",
    )
    args = ap.parse_args()

    if args.family_only and args.clinician_only:
        ap.error("--family-only and --clinician-only are mutually exclusive; "
                 "omit both to render the two-register document")

    path = Path(args.findings)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON — {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("error: findings JSON must be an object", file=sys.stderr)
        return 1

    parts = []
    if not args.clinician_only:
        family = render_family(data)
        parts.append(family)
        for note in check_family_register(family):
            print(f"register: {note}", file=sys.stderr)
    if not args.family_only:
        parts.append(render_clinician(data))

    document = "\n\n---\n\n".join(p.strip() for p in parts) + "\n"

    leaks = check_deidentified(document)
    if leaks:
        print(
            "warning: output may contain identifiable data — "
            + ", ".join(leaks)
            + ". Remove before sharing.",
            file=sys.stderr,
        )
        # A warning on stderr is easy to miss, and this document is meant to be
        # handed to a clinic. Writing the file is the step that makes the leak
        # durable, so that step is the one that stops.
        if args.out and not args.allow_phi:
            print(
                f"error: refusing to write {args.out} — remove the identifiers above, "
                "or pass --allow-phi if this is intentional.",
                file=sys.stderr,
            )
            return 1

    if args.out:
        Path(args.out).write_text(document)
        print(f"wrote {args.out}")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())