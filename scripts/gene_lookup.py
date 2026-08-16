#!/usr/bin/env python3
"""
Look up a gene or CNV region in the curated care index.

Returns the associated syndrome, authoritative sources to FETCH, the care
domains those sources cover (split by risk tier), gene-specific traps, and
patient organisations.

It does NOT return screening ages, intervals, modalities, or drug doses. Those
drift between guideline versions and must be read from the cited source with a
retrieval date. See references/risk_layer_policy.md.

Usage:
    python gene_lookup.py PTEN
    python gene_lookup.py SCN2A --json
    python gene_lookup.py --cnv 22q11.2 --copies 1
    python gene_lookup.py --list
"""

import argparse
import json
import sys
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parent.parent / "assets" / "gene_index.json"

NOT_FOUND_GUIDANCE = """\
Not in the curated index. That does not mean there is no guidance — it means
this index has not curated it. Search, in order:

  1. GeneReviews   https://www.ncbi.nlm.nih.gov/books/NBK1116/
  2. ClinGen       https://clinicalgenome.org/
  3. OMIM          https://www.omim.org/
  4. SFARI Gene    https://gene.sfari.org/
  5. Recent literature

Then report honestly how much established guidance exists. "There is no
published surveillance protocol for this gene" is a valid and useful answer
that families rarely get."""


def load_index() -> dict:
    if not INDEX_PATH.exists():
        print(f"error: index not found at {INDEX_PATH}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(INDEX_PATH.read_text())


def resolve(index: dict, gene: str) -> tuple[str, dict] | None:
    """Resolve a gene symbol, following `same_as` aliases."""
    genes = index["genes"]
    key = gene.upper()
    if key not in genes:
        return None
    entry = genes[key]
    seen = {key}
    while "same_as" in entry:
        key = entry["same_as"]
        if key in seen:  # cycle guard
            break
        seen.add(key)
        entry = genes[key]
    return key, entry


def match_cnv(index: dict, band: str, copies: int | None) -> list[tuple[str, dict]]:
    band_norm = band.lower().replace(" ", "")
    hits = []
    for key, region in index["cnv_regions"].items():
        if region["band"].lower().replace(" ", "").startswith(band_norm[:6]):
            if copies is None or region.get("copies") == copies:
                hits.append((key, region))
    return hits


def render(name: str, entry: dict, resolved_from: str | None = None) -> str:
    lines: list[str] = []
    header = f"## {name} — {entry.get('syndrome', 'syndrome not recorded')}"
    lines.append(header)
    if resolved_from and resolved_from != name:
        lines.append(f"_(resolved from {resolved_from})_")
    if entry.get("aliases"):
        lines.append(f"Also known as: {', '.join(entry['aliases'])}")
    lines.append("")

    t1 = entry.get("tier1_domains") or []
    t2 = entry.get("tier2_domains") or []

    lines.append("### Tier 1 — established surveillance domains")
    if t1:
        for d in t1:
            lines.append(f"  - {d}")
        lines.append("")
        lines.append("  Fetch the source below for the actual protocol. Do NOT state ages,")
        lines.append("  intervals, or modalities from memory.")
    else:
        lines.append("  None recorded. Do not invent one.")
    lines.append("")

    lines.append("### Tier 2 — documented associations, no formal protocol")
    if t2:
        for d in t2:
            lines.append(f"  - {d}")
        lines.append("")
        lines.append("  Frame as: more common but not inevitable · what it looks like ·")
        lines.append("  manageable when identified · who to raise it with.")
    else:
        lines.append("  None recorded.")
    lines.append("")

    if entry.get("traps"):
        lines.append("### Gene-specific traps — read these before writing")
        for t in entry["traps"]:
            lines.append(f"  ! {t}")
        lines.append("")

    lines.append("### Sources to fetch")
    for s in entry.get("sources", []):
        bits = [s["name"]]
        if s.get("journal"):
            bits.append(s["journal"])
        if s.get("year"):
            bits.append(str(s["year"]))
        lines.append(f"  - {', '.join(bits)}")
        lines.append(f"    {s['url']}")
    lines.append("")

    if entry.get("organisations"):
        lines.append("### Patient organisations")
        for o in entry["organisations"]:
            lines.append(f"  - {o['name']}: {o['url']}")
        lines.append("")

    lines.append("### Always also check")
    lines.append("  - Simons Searchlight (registry, enrols by gene): https://www.simonssearchlight.org/")
    lines.append("  - ClinicalTrials.gov — search gene symbol AND syndrome name")
    lines.append("")
    lines.append("Reminder: retrieve specifics and cite with a retrieval date. "
                 "Never recite ages, intervals, or doses from memory.")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("gene", nargs="?", help="Gene symbol, e.g. PTEN")
    ap.add_argument("--cnv", help="Cytoband, e.g. 22q11.2")
    ap.add_argument("--copies", type=int, help="Copy number: 1 = deletion, 3 = duplication")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON")
    ap.add_argument("--list", action="store_true", help="List everything curated")
    args = ap.parse_args()

    index = load_index()

    if args.list:
        print("Genes:")
        for k, v in sorted(index["genes"].items()):
            target = v.get("same_as")
            label = f"→ {target}" if target else v.get("syndrome", "")
            print(f"  {k:<10} {label}")
        print("\nCNV regions:")
        for k, v in sorted(index["cnv_regions"].items()):
            print(f"  {k:<28} {v.get('syndrome','')}")
        return 0

    if args.cnv:
        hits = match_cnv(index, args.cnv, args.copies)
        if not hits:
            print(f"No curated region matching {args.cnv}"
                  f"{f' with {args.copies} copies' if args.copies else ''}.\n")
            print(NOT_FOUND_GUIDANCE)
            return 0
        if args.json:
            print(json.dumps({k: v for k, v in hits}, indent=2))
            return 0
        for key, region in hits:
            print(render(key, region))
            print()
        return 0

    if not args.gene:
        ap.error("provide a gene symbol, --cnv, or --list")
        return 2

    found = resolve(index, args.gene)
    if not found:
        print(f"{args.gene.upper()}: not in the curated index.\n")
        print(NOT_FOUND_GUIDANCE)
        return 0

    key, entry = found
    if args.json:
        print(json.dumps({key: entry}, indent=2))
    else:
        print(render(key, entry, resolved_from=args.gene.upper()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())