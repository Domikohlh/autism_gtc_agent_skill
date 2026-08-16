#!/usr/bin/env python3
"""
Extract structured findings from a genetic test report.

Handles plain text, PDF (via pdfplumber or pdftotext), and VCF. Emits JSON.

This is a first-pass extractor: it finds candidate fields and flags what it is
unsure about. It is deliberately conservative — it would rather report
`needs_review` than assert a wrong variant string. Always eyeball the output
against the source before using it.

Usage:
    python parse_report.py report.pdf
    python parse_report.py report.txt --json out.json
    python parse_report.py --text "SCN2A c.5645G>A p.(Arg1882Gln) heterozygous, pathogenic"
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

# HGVS coding change, with optional transcript prefix and protein consequence.
HGVS_C = re.compile(
    r"(?:(?P<transcript>N[MR]_\d+(?:\.\d+)?)\s*(?:\((?P<gene_in_paren>[A-Z0-9orf\-]+)\))?\s*:?\s*)?"
    r"(?P<c>c\.[\d\-\+\*_]+(?:[ACGT]+>[ACGT]+|del[ACGT]*|dup[ACGT]*|ins[ACGT]+|delins[ACGT]+|=))",
    re.IGNORECASE,
)

HGVS_P = re.compile(
    r"p\.\(?(?P<p>[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2}|Ter|\*|fs(?:Ter\d+|\*\d+)?|=)?)\)?"
)

# Explicitly labelled gene field — the authoritative source when present.
GENE_LABEL = re.compile(
    r"\bGene(?:\s*(?:name|symbol))?\s*[::]\s*(?P<gene>[A-Z][A-Z0-9\-]{1,9}(?:orf\d+)?)\b",
    re.IGNORECASE,
)

# Bare transcript accession, for the common layout where it sits on its own line.
TRANSCRIPT = re.compile(r"\b(?P<transcript>N[MR]_\d+(?:\.\d+)?)\b")

# Bare gene symbol: uppercase alphanumeric, 2-10 chars. Noisy by design —
# used only as a last resort, filtered against a stop-list.
GENE_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:orf\d+)?)\b")

CNV = re.compile(
    r"(?:arr\s*)?\[?(?P<build>GRCh3[78]|hg19|hg38)?\]?\s*"
    r"(?P<band>\d{1,2}[pq]\d{1,2}(?:\.\d+)?)\s*"
    r"\(\s*(?P<start>[\d,]+)\s*[-_]\s*(?P<end>[\d,]+)\s*\)\s*"
    r"x\s*(?P<copies>\d)",
    re.IGNORECASE,
)

CLASSIFICATIONS = [
    ("likely pathogenic", "Likely pathogenic"),
    ("pathogenic", "Pathogenic"),
    ("likely benign", "Likely benign"),
    ("benign", "Benign"),
    ("uncertain significance", "VUS"),
    ("unknown significance", "VUS"),
    (r"\bvus\b", "VUS"),
    ("class 3", "VUS"),
]

ZYGOSITY = [
    ("homozygous", "homozygous"),
    ("heterozygous", "heterozygous"),
    ("hemizygous", "hemizygous"),
    ("compound heterozygous", "compound heterozygous"),
    ("mosaic", "mosaic"),
]

INHERITANCE = [
    ("de novo", "de novo"),
    ("maternally inherited", "maternal"),
    ("paternally inherited", "paternal"),
    ("inherited from mother", "maternal"),
    ("inherited from father", "paternal"),
]

TEST_TYPES = [
    ("genome sequencing", "genome"),
    ("whole genome", "genome"),
    ("exome sequencing", "exome"),
    ("whole exome", "exome"),
    ("chromosomal microarray", "microarray"),
    ("microarray", "microarray"),
    (r"\bcma\b", "microarray"),
    ("gene panel", "panel"),
    ("karyotype", "karyotype"),
    (r"\bfish\b", "FISH"),
    ("repeat expansion", "repeat expansion"),
]

DATE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)

SECONDARY_FINDING_CUES = [
    "secondary finding",
    "incidental finding",
    "acmg sf",
    "medically actionable finding",
]

# Tokens that look like gene symbols but aren't, in this document context.
GENE_STOPLIST = {
    "DNA", "RNA", "PCR", "NGS", "CNV", "SNV", "VUS", "ACMG", "AMP", "CLIA", "CAP",
    "ID", "ASD", "ADHD", "MRI", "EEG", "ECG", "EKG", "GRCH37", "GRCH38", "HG19",
    "HG38", "NM", "NP", "NC", "OMIM", "HPO", "MANE", "REF", "ALT", "QC", "TAT",
    "PDF", "USA", "UK", "MD", "PHD", "MS", "MSC", "BSC", "II", "III", "IV",
    "A", "T", "C", "G", "N", "X", "Y", "AD", "AR", "XL", "XLR", "XLD", "IGV",
    "HGVS", "LOH", "AOH", "UPD", "FDA", "NHS", "EDTA", "GT", "AF", "DP",
}


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Variant:
    gene: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    classification: str | None = None
    zygosity: str | None = None
    inheritance: str | None = None
    raw_context: str = ""
    needs_review: list[str] = field(default_factory=list)


@dataclass
class CopyNumberVariant:
    band: str | None = None
    build: str | None = None
    start: int | None = None
    end: int | None = None
    copies: int | None = None
    size_bp: int | None = None
    classification: str | None = None
    raw_context: str = ""


@dataclass
class ReportRecord:
    source_file: str | None = None
    test_type: str | None = None
    report_date: str | None = None
    variants: list[Variant] = field(default_factory=list)
    cnvs: list[CopyNumberVariant] = field(default_factory=list)
    secondary_findings_mentioned: bool = False
    candidate_dates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Text extraction
# --------------------------------------------------------------------------

def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix == ".vcf":
        return path.read_text(errors="replace")
    return path.read_text(errors="replace")


def read_pdf(path: Path) -> str:
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(path)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except ImportError:
        pass

    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Could not read PDF. Install pdfplumber (`pip install pdfplumber "
            "--break-system-packages`) or poppler-utils for pdftotext."
        ) from exc


# --------------------------------------------------------------------------
# Field detection
# --------------------------------------------------------------------------

def find_first(text: str, patterns: list[tuple[str, str]]) -> str | None:
    """Return the label of the earliest-matching pattern in `text`."""
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for pattern, label in patterns:
        m = re.search(pattern, lowered)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), label)
    return best[1] if best else None


def window(text: str, start: int, end: int, pad: int = 220) -> str:
    return " ".join(text[max(0, start - pad):min(len(text), end + pad)].split())


def resolve_gene(before: str, inline: str | None) -> tuple[str | None, str]:
    """
    Return (gene, provenance).

    Reports are block-structured: the gene and transcript for a variant appear
    just above it. So we take the LAST labelled gene before the variant, which
    is the one belonging to this block — not the first token we happen to see.

    Provenance is reported so downstream can distinguish a gene read from a
    label (trustworthy) from one guessed out of prose (must be verified).
    """
    if inline:
        return inline.upper(), "transcript parentheses"

    labels = GENE_LABEL.findall(before)
    if labels:
        return labels[-1].upper(), "labelled 'Gene:' field"

    candidates = [
        t for t in GENE_TOKEN.findall(before)
        if t.upper() not in GENE_STOPLIST and not t.isdigit()
    ]
    if candidates:
        return candidates[-1].upper(), "inferred from surrounding text"

    return None, "not found"


def parse_variants(text: str) -> list[Variant]:
    """
    Segment the document into one block per variant before extracting fields.

    Without segmentation, a fixed-width context window pulls the neighbouring
    variant's zygosity, classification, and protein change into the wrong
    record — which is worse than missing them, because it looks correct.

    Each block runs from the end of the previous HGVS match to the start of the
    next one. Within a block: gene and transcript are read backwards from the
    variant (they precede it in report layout); classification, zygosity,
    inheritance and the protein change are read forwards.
    """
    matches = list(HGVS_C.finditer(text))
    variants: list[Variant] = []

    for i, m in enumerate(matches):
        block_start = matches[i - 1].end() if i > 0 else 0
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        before = text[block_start:m.start()]
        after = text[m.end():block_end]

        gene, provenance = resolve_gene(before, m.group("gene_in_paren"))

        transcript = m.group("transcript")
        if not transcript:
            found = TRANSCRIPT.findall(before)
            transcript = found[-1] if found else None

        v = Variant(
            gene=gene,
            transcript=transcript,
            hgvs_c=m.group("c"),
            classification=find_first(after, CLASSIFICATIONS),
            zygosity=find_first(after, ZYGOSITY),
            inheritance=find_first(after, INHERITANCE),
            raw_context=" ".join(f"{before[-160:]} >>>{m.group('c')}<<< {after[:200]}".split()),
        )

        p_match = HGVS_P.search(after) or HGVS_P.search(before)
        if p_match:
            v.hgvs_p = "p." + p_match.group("p")

        if provenance == "inferred from surrounding text":
            v.needs_review.append("gene symbol inferred from surrounding text — verify against source")
        elif provenance == "not found":
            v.needs_review.append("no gene symbol found for this variant — read the source")
        if not v.transcript:
            v.needs_review.append("no transcript found — confirm which transcript was used")
        if not v.classification:
            v.needs_review.append("no classification found in this variant's block")
        if not v.zygosity:
            v.needs_review.append("zygosity not found")

        variants.append(v)

    return dedupe_variants(variants)


def dedupe_variants(variants: list[Variant]) -> list[Variant]:
    seen: dict[tuple, Variant] = {}
    for v in variants:
        key = (v.gene, v.hgvs_c)
        if key not in seen:
            seen[key] = v
        else:
            # Keep the record with more fields populated.
            existing = seen[key]
            score = lambda x: sum(
                1 for f in (x.transcript, x.hgvs_p, x.classification, x.zygosity, x.inheritance)
                if f
            )
            if score(v) > score(existing):
                seen[key] = v
    return list(seen.values())


def parse_cnvs(text: str) -> list[CopyNumberVariant]:
    cnvs = []
    for m in CNV.finditer(text):
        ctx = window(text, m.start(), m.end())
        start = int(m.group("start").replace(",", ""))
        end = int(m.group("end").replace(",", ""))
        cnvs.append(
            CopyNumberVariant(
                band=m.group("band"),
                build=m.group("build"),
                start=start,
                end=end,
                copies=int(m.group("copies")),
                size_bp=abs(end - start),
                classification=find_first(ctx, CLASSIFICATIONS),
                raw_context=ctx,
            )
        )
    return cnvs


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def parse(text: str, source: str | None = None) -> ReportRecord:
    rec = ReportRecord(source_file=source)

    rec.test_type = find_first(text, TEST_TYPES)
    rec.variants = parse_variants(text)
    rec.cnvs = parse_cnvs(text)

    lowered = text.lower()
    rec.secondary_findings_mentioned = any(cue in lowered for cue in SECONDARY_FINDING_CUES)

    dates = DATE.findall(text)
    rec.candidate_dates = list(dict.fromkeys(dates))[:6]
    if rec.candidate_dates:
        rec.report_date = rec.candidate_dates[0]

    if not rec.variants and not rec.cnvs:
        rec.warnings.append(
            "No variants or CNVs detected. The report may be negative, may be an image "
            "requiring OCR, or may use a format this parser does not recognise. "
            "Read it directly."
        )
    if not rec.test_type:
        rec.warnings.append(
            "Test type not identified — this changes what the result could have found. Ask."
        )
    if not rec.report_date:
        rec.warnings.append(
            "Report date not identified — needed to assess whether reanalysis is due. Ask."
        )
    if rec.secondary_findings_mentioned:
        rec.warnings.append(
            "Secondary/incidental findings referenced. Apply the secondary findings rules "
            "in references/risk_layer_policy.md — flag and route, do not counsel."
        )
    if any("gene symbol inferred" in w for v in rec.variants for w in v.needs_review):
        rec.warnings.append(
            "At least one gene symbol was inferred rather than read from a transcript. "
            "Verify against the source before using."
        )

    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="Report file (.pdf, .txt, .vcf)")
    ap.add_argument("--text", help="Parse a literal string instead of a file")
    ap.add_argument("--json", help="Write JSON to this path instead of stdout")
    args = ap.parse_args()

    if args.text:
        record = parse(args.text, source=None)
    elif args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"error: {path} not found", file=sys.stderr)
            return 1
        record = parse(read_text(path), source=str(path))
    else:
        ap.error("provide a file path or --text")
        return 2

    payload = json.dumps(asdict(record), indent=2)
    if args.json:
        Path(args.json).write_text(payload)
        print(f"wrote {args.json}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())