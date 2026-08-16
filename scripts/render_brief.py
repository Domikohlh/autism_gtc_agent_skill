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

import argparse
import json
import re
import sys
from pathlib import Path

LIMITS_BLOCK = (
    "> **What this document is and isn't.** This summarises published information "
    "about this genetic finding. It is not medical advice, not a diagnosis, and not "
    "a prediction. Every decision belongs with the clinical team — bring this to them."
)

# Patterns that suggest identifiable data leaked into the output.
PHI_PATTERNS = [
    (re.compile(r"\bMRN[:\s#]*\d+", re.I), "medical record number"),
    (re.compile(r"\bDOB[:\s]*\d", re.I), "date of birth"),
    (re.compile(r"\bNHS\s*(?:no\.?|number)[:\s]*\d", re.I), "NHS number"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "possible SSN"),
    (re.compile(r"\baccession[:\s#]*\w{4,}", re.I), "lab accession number"),
]


def check_deidentified(text: str) -> list[str]:
    return [label for pattern, label in PHI_PATTERNS if pattern.search(text)]


def section(title: str, body: str | None, level: int = 2) -> str:
    """Render a section, or nothing at all if the body is empty."""
    if not body or not str(body).strip():
        return ""
    return f"{'#' * level} {title}\n\n{str(body).strip()}\n\n"


def render_family(data: dict) -> str:
    fam = data.get("family", {})
    out = ["# Understanding this genetic result\n"]

    if data.get("urgent"):
        out.append("> **Please raise these with a doctor promptly:**\n>")
        for item in data["urgent"]:
            out.append(f"> - {item}")
        out.append("")

    out.append(section("What was found", fam.get("what_was_found")))
    out.append(section("What this means", fam.get("what_this_means")))
    out.append(section("What this does not mean", fam.get("what_this_does_not_mean")))
    out.append(section("Health monitoring that goes with this finding", fam.get("tier1_monitoring")))
    out.append(section("Things worth knowing about", fam.get("tier2_awareness")))
    out.append(section("Where to find others", fam.get("where_to_find_others")))

    questions = fam.get("questions") or []
    if questions:
        out.append("## Questions to bring to your next appointment\n")
        for q in questions:
            out.append(f"- {q}")
        out.append("")

    out.append(LIMITS_BLOCK + "\n")
    return "\n".join(p for p in out if p is not None)


def render_clinician(data: dict) -> str:
    clin = data.get("clinician", {})
    out = ["# Genomic result summary — clinician section\n"]

    if data.get("urgent"):
        out.append("> **Time-critical:**\n>")
        for item in data["urgent"]:
            out.append(f"> - {item}")
        out.append("")

    table = clin.get("finding_table") or {}
    if table:
        out.append("## Finding\n")
        out.append("| Field | Value |")
        out.append("|---|---|")
        for k, v in table.items():
            out.append(f"| {k} | {v if v not in (None, '') else '—'} |")
        out.append("")

    out.append(section("Gene–disease association", clin.get("gene_disease_association")))
    out.append(section("Established surveillance — Tier 1", clin.get("tier1_surveillance")))
    out.append(section("Documented associations without formal protocol — Tier 2", clin.get("tier2_associations")))
    out.append(section("Management considerations", clin.get("management_considerations")))
    out.append(section("Secondary findings", clin.get("secondary_findings")))
    out.append(section("Uncertainty and limitations", clin.get("uncertainty")))
    out.append(section("Suggested next steps", clin.get("next_steps")))

    sources = clin.get("sources") or []
    if sources:
        out.append("## Sources\n")
        for i, s in enumerate(sources, 1):
            text = s.get("text", "")
            url = s.get("url", "")
            retrieved = s.get("retrieved", "")
            line = f"{i}. {text}"
            if url:
                line += f" — {url}"
            if retrieved:
                line += f" _(retrieved {retrieved})_"
            out.append(line)
        out.append("")
    else:
        out.append("## Sources\n")
        out.append("_No sources recorded. This is a problem — every clinical assertion "
                   "above needs a source and a retrieval date._\n")

    out.append(LIMITS_BLOCK + "\n")
    return "\n".join(p for p in out if p is not None)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("findings", help="Structured findings JSON")
    ap.add_argument("--out", help="Write to this path (default: stdout)")
    ap.add_argument("--family-only", action="store_true")
    ap.add_argument("--clinician-only", action="store_true")
    args = ap.parse_args()

    path = Path(args.findings)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON — {exc}", file=sys.stderr)
        return 1

    parts = []
    if not args.clinician_only:
        parts.append(render_family(data))
    if not args.family_only:
        parts.append(render_clinician(data))

    document = "\n\n---\n\n".join(parts)

    leaks = check_deidentified(document)
    if leaks:
        print(
            "warning: output may contain identifiable data — "
            + ", ".join(leaks)
            + ". Remove before sharing.",
            file=sys.stderr,
        )

    if args.out:
        Path(args.out).write_text(document)
        print(f"wrote {args.out}")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())