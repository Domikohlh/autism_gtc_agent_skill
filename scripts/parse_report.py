#!/usr/bin/env python3
"""
Extract structured findings from a genetic test report.

Handles plain text, PDF (via pdfplumber or pdftotext), and VCF. Emits JSON.

Format is detected from content, not from the file extension, so a VCF renamed
to .txt — which several upload platforms require — parses identically.

This is a first-pass extractor: it finds candidate fields and flags what it is
unsure about. It is deliberately conservative — it would rather report
`needs_review` than assert a wrong variant string. Always eyeball the output
against the source before using it.

Identifiers (name, DOB, record/hospital number, NHS number, accession, email)
are redacted from the whole document before parsing begins, and dates labelled
as birth or collection dates are never surfaced. The ruleset is in phi.py,
shared with render_brief.py. Pass --no-redact only when debugging against a
synthetic report.

Usage:
    python parse_report.py report.pdf
    python parse_report.py report.txt --json out.json
    python parse_report.py --text "SCN2A c.5645G>A p.(Arg1882Gln) heterozygous, pathogenic"
    python parse_report.py annotated.vcf        # or annotated.vcf.txt — content decides
"""

from __future__ import annotations


import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    from phi import DATE_SRC, redact
except ImportError:  # imported as a module from outside scripts/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phi import DATE_SRC, redact

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
# The colon class covers the fullwidth variant, which turns up in PDF exports.
GENE_LABEL = re.compile(
    r"\bGene(?:\s*(?:name|symbol))?\s*[:：]\s*(?P<gene>[A-Z][A-Z0-9\-]{1,9}(?:orf\d+)?)\b",
    re.IGNORECASE,
)

# Bare transcript accession, for the common layout where it sits on its own line.
TRANSCRIPT = re.compile(r"\b(?P<transcript>N[MR]_\d+(?:\.\d+)?)\b")

# Bare gene symbol: uppercase alphanumeric, 2-10 chars. Noisy by design —
# used only as a last resort, filtered against a stop-list.
GENE_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:orf\d+)?)\b")

# Cytoband, including the sex chromosomes.
BAND = r"(?:\d{1,2}|[XY])[pq]\d{1,2}(?:\.\d+)?"

# ISCN copy-number notation: the authoritative form when the report uses it.
CNV = re.compile(
    r"(?:arr\s*)?\[?(?P<build>GRCh3[78]|hg19|hg38)?\]?\s*"
    rf"(?P<band>{BAND})\s*"
    r"\(\s*(?P<start>[\d,]+)\s*[-_]\s*(?P<end>[\d,]+)\s*\)\s*"
    r"x\s*(?P<copies>\d)",
    re.IGNORECASE,
)

# Prose copy-number statements. Families paste these, and many reports word the
# summary line this way even when the ISCN string appears elsewhere. Without
# these the CNV never reaches gene_lookup.py --cnv, which is where the Tier 1
# content for recurrent regions lives.
#
# What may sit between the band and the word "deletion" is a whitelist, not a
# wildcard gap. A wildcard reads "a duplication at 16p11.2 and a deletion
# involving Xp22.31" as a 16p11.2 deletion — inventing a finding, then routing
# it to genuine Tier 1 surveillance content. That is the worst failure this
# script could produce, and it is worth losing some unusual phrasings to avoid.
_CNV_KIND = r"(?P<kind>microdeletion|microduplication|deletion|duplication|loss|gain)"
_CNV_ADJ = (
    r"(?:(?:interstitial|terminal|intragenic|heterozygous|homozygous|hemizygous|mosaic"
    r"|recurrent|de\s+novo|apparently\s+balanced|likely\s+pathogenic|pathogenic"
    r"|copy\s+number|chromosom(?:e|al))\s+){0,3}"
)
_CNV_PREP = r"\s+(?:at|of|in|on|involving|spanning|encompassing|within|affecting|includ\w+)(?:\s+the)?\s+"

CNV_PROSE_SIZE_FIRST = re.compile(
    r"\b(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>kb|mb|bp)\b\s+" + _CNV_ADJ + _CNV_KIND
    + _CNV_PREP + rf"(?P<band>{BAND})\b",
    re.IGNORECASE,
)
CNV_PROSE_BAND_FIRST = re.compile(
    rf"\b(?P<band>{BAND})\b\s+(?:region\s+|locus\s+)?" + _CNV_ADJ + _CNV_KIND,
    re.IGNORECASE,
)
CNV_PROSE_KIND_FIRST = re.compile(
    r"\b" + _CNV_ADJ + _CNV_KIND + _CNV_PREP + rf"(?P<band>{BAND})\b",
    re.IGNORECASE,
)

# Reports routinely name the *other* syndrome to contrast it — "the reciprocal
# 16p11.2 deletion and this duplication have partly differing features". Read
# literally that is a second finding, and for 16p11.2 it is a finding with the
# opposite phenotype to the real one. Matched against the text just before the
# statement.
CNV_REFERENTIAL = re.compile(
    r"(?:reciprocal|in\s+contrast(?:\s+to)?|as\s+opposed\s+to|unlike|whereas|instead\s+of"
    r"|rather\s+than|no\s+evidence\s+of|absence\s+of|does\s+not\s+(?:detect|exclude)"
    r"|distinguish(?:ed)?\s+from|compared\s+(?:to|with))"
    r"(?:\s+(?:the|a|an|this|that|its))?\s*$",
    re.IGNORECASE,
)

# Repeat expansions. FMR1 is the canonical case: repeat sizing is a separate
# assay, it is the single most-missed result in an autism/ID workup, and the
# HGVS patterns above cannot see it at all.
REPEAT_CUE = re.compile(
    r"(?:\b(?P<motif>CGG|CAG|CTG|GAA|CCG|GCC)\s*(?:triplet\s*)?repeat"
    r"|\(\s*(?P<motif2>[ACGT]{3,6})\s*\)\s*n"
    r"|\brepeat\s+expansion\b|\btriplet\s+repeat\b|\brepeat\s+siz\w*\b"
    r"|\brepeat\s+(?:analysis|number|length)\b)",
    re.IGNORECASE,
)
REPEAT_COUNT = re.compile(
    r"\b(?P<n>\d{1,4})\s*(?:CGG|CAG|CTG|GAA|CCG|GCC)?\s*repeats?\b", re.IGNORECASE
)
REPEAT_ALLELES = re.compile(
    r"\balleles?\s*[:：]?\s*(?P<a>\d{1,4})\s*(?:and|,|/|&)\s*(?P<b>\d{1,4})", re.IGNORECASE
)

# Almost every exome and microarray report says, in its limitations paragraph,
# that the assay does not detect repeat expansions. Read literally that is a
# repeat result, and because it makes `repeats` non-empty it also suppresses the
# "nothing detected" warning — so a negative report came back with a fabricated
# finding and no warnings at all. The plural "expansions" happened to escape the
# `\b` in the cue; the singular did not, which is luck rather than design.
#
# Same shape as CNV_REFERENTIAL: matched against the sentence the cue sits in.
REPEAT_NEGATED = re.compile(
    r"(?:does\s+not\s+(?:detect|include|cover|assess|analy[sz]e|reliably)"
    r"|cannot\s+(?:detect|be\s+detected|exclude)|will\s+not\s+detect|unable\s+to\s+detect"
    r"|not\s+(?:detected|assessed|analy[sz]ed|performed|tested|examined|included|covered|reported)"
    r"|no\s+(?:evidence\s+of|expansion)|excluded\s+from|outside\s+the\s+scope"
    r"|beyond\s+the\s+scope|limitations?\s*[:：]|separate\s+assay\s+is\s+required)",
    re.IGNORECASE,
)

REPEAT_CATEGORIES = [
    ("full mutation", "full mutation"),
    ("pre-?mutation", "premutation"),
    ("intermediate", "intermediate"),
    ("gr[ea]y zone", "intermediate"),
    ("normal range", "normal"),
]

# Two-stage: a specific status if one is stated, and only otherwise the generic
# note. As one list, "Methylation status: fully methylated" matches the generic
# "methylation" first — earlier in the string — and loses the actual answer.
METHYLATION_SPECIFIC = [
    ("fully methylated", "fully methylated"),
    ("partially methylated", "partially methylated"),
    ("abnormally methylated", "abnormally methylated"),
    ("unmethylated", "unmethylated"),
    ("not methylated", "unmethylated"),
]
METHYLATION_GENERIC = re.compile(r"methylat", re.IGNORECASE)

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

# DATE_SRC is imported from phi, which needs it for the date-of-birth rule.
DATE = re.compile(rf"\b(?:{DATE_SRC})\b", re.IGNORECASE)

# Which date is the report date matters: staleness drives the reanalysis
# recommendation, and the first date on a report is almost always the date of
# birth. Both label sets are anchored to the text immediately preceding a date.
REPORT_DATE_LABEL = re.compile(
    r"(?:date\s+of\s+report|report(?:ing)?\s+date|date\s+report(?:ed)?|reported(?:\s+on)?"
    r"|date\s+of\s+issue|date\s+issued|issued(?:\s+on)?|signed[\s-]?out(?:\s+on)?"
    r"|authoris(?:ed|zed)(?:\s+on)?|results?\s+date|date\s+of\s+results?"
    # Enough non-English labels to keep a foreign report from falling back to a
    # date of birth. Fields elsewhere will still be missed — that is flagged,
    # not silently guessed.
    r"|befunddatum|berichtsdatum|datum\s+des\s+befund(?:e|es)?"
    r"|fecha\s+del?\s+informe|date\s+du\s+rapport|data\s+del\s+referto)"
    r"\s*[:：]?\s*$",
    re.IGNORECASE,
)
NON_REPORT_DATE_LABEL = re.compile(
    r"(?:d\.?o\.?b\.?|date\s+of\s+birth|birth\s*date|born(?:\s+on)?"
    r"|date\s+of\s+collection|collect(?:ed|ion)(?:\s+date)?|date\s+collected"
    r"|receiv(?:ed|al)(?:\s+date)?|date\s+received|drawn(?:\s+on)?|date\s+drawn"
    r"|accession(?:\s+date)?|specimen\s+date|sample\s+date"
    r"|referral\s+date|date\s+of\s+referral|requested(?:\s+on)?|date\s+requested"
    r"|geburtsdatum|geb\.|eingangsdatum|entnahmedatum|abnahmedatum"
    r"|fecha\s+de\s+nacimiento|date\s+de\s+naissance|data\s+di\s+nascita)"
    r"\s*[:：]?\s*$",
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
    "CHROM", "POS", "QUAL", "FILTER", "INFO", "FORMAT", "PASS", "VCF", "ANN",
    "CSQ", "CLNSIG", "MODERATE", "HIGH", "LOW",
    # Words left behind by redaction, which would otherwise look like symbols
    # to the last-resort gene guesser.
    "NAME", "REDACTED", "DOB", "MRN", "RECORD", "NUMBER", "ACCESSION", "EMAIL",
    "SSN", "SHAPED",
}

# --------------------------------------------------------------------------
# De-identification
# --------------------------------------------------------------------------

# The ruleset lives in phi.py and is shared with render_brief.py, so that the
# script writing the final document and the script reading the report agree on
# what an identifier is. They did not, and the renderer's list was the shorter
# one. `redact` is imported at the top of this file.


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Variant:
    gene: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    genomic: str | None = None
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
    kind: str | None = None
    size_bp: int | None = None
    classification: str | None = None
    provenance: str = "ISCN notation"
    raw_context: str = ""
    needs_review: list[str] = field(default_factory=list)


@dataclass
class RepeatExpansion:
    gene: str | None = None
    motif: str | None = None
    allele_sizes: list[int] = field(default_factory=list)
    category: str | None = None
    methylation: str | None = None
    raw_context: str = ""
    needs_review: list[str] = field(default_factory=list)


@dataclass
class ReportRecord:
    source_file: str | None = None
    test_type: str | None = None
    report_date: str | None = None
    report_date_provenance: str | None = None
    variants: list[Variant] = field(default_factory=list)
    cnvs: list[CopyNumberVariant] = field(default_factory=list)
    repeats: list[RepeatExpansion] = field(default_factory=list)
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
    return path.read_text(errors="replace")


SCANNED_PDF_HINT = (
    "No text could be extracted. If this is a scanned or photographed report, "
    "it needs OCR first (e.g. `ocrmypdf in.pdf out.pdf`). Afterwards, verify the "
    "variant string character by character against the original — a misread "
    "c.1234G>A vs c.1234C>A is a different variant."
)


def read_pdf(path: Path) -> str:
    """
    Extract text from a PDF, trying pdfplumber then pdftotext.

    Both routes are attempted before giving up, and failures report what to do
    next rather than surfacing a traceback. Reports reach this tool as scans and
    phone photographs often enough that the unreadable-PDF path is a normal
    case, not an exceptional one.
    """
    attempts: list[str] = []

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(path)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        if text.strip():
            return text
        attempts.append("pdfplumber opened the file but found no text layer")
    except ImportError:
        attempts.append("pdfplumber not installed")
    except Exception as exc:  # malformed, encrypted, or otherwise unreadable
        attempts.append(f"pdfplumber failed: {type(exc).__name__}: {exc}")

    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, check=True,
        )
        if out.stdout.strip():
            return out.stdout
        attempts.append("pdftotext ran but found no text layer")
    except FileNotFoundError:
        attempts.append("pdftotext not available (install poppler-utils)")
    except subprocess.CalledProcessError as exc:
        attempts.append(f"pdftotext failed: {exc.stderr.strip() or exc}")

    detail = "\n".join(f"  - {a}" for a in attempts)

    if any("no text layer" in a for a in attempts):
        hint = SCANNED_PDF_HINT
    elif all("not installed" in a or "not available" in a for a in attempts):
        hint = ("No PDF reader available. Install one of: `pip install pdfplumber` "
                "or poppler-utils for pdftotext.")
    else:
        hint = ("A PDF reader was available but could not open this file — it may be "
                "corrupt, truncated, or password-protected. Try opening it manually, "
                "re-exporting it, or ask for the report as text.")

    raise RuntimeError(f"Could not read {path.name}.\n{detail}\n\n{hint}")


# --------------------------------------------------------------------------
# Field detection
# --------------------------------------------------------------------------

def find_first(text: str, patterns: list[tuple[str, str]]) -> str | None:
    """
    Return the label of the earliest-matching pattern in `text`.

    Ties on start position are broken towards the longer match, so "likely
    pathogenic" wins over the "pathogenic" nested inside it.
    """
    lowered = text.lower()
    best: tuple[tuple[int, int], str] | None = None
    for pattern, label in patterns:
        m = re.search(pattern, lowered)
        if m:
            key = (m.start(), -m.end())
            if best is None or key < best[0]:
                best = (key, label)
    return best[1] if best else None


def find_last(text: str, patterns: list[tuple[str, str]]) -> str | None:
    """
    Return the label of the latest-matching pattern in `text`.

    Used when reading backwards from a variant in a column layout: the nearest
    preceding match is the one belonging to this row. Ties on end position are
    broken towards the longer match, for the same reason as `find_first`.
    """
    lowered = text.lower()
    best: tuple[tuple[int, int], str] | None = None
    for pattern, label in patterns:
        for m in re.finditer(pattern, lowered):
            key = (m.end(), -m.start())
            if best is None or key > best[0]:
                best = (key, label)
    return best[1] if best else None


def window(text: str, start: int, end: int, pad: int = 220) -> str:
    return " ".join(text[max(0, start - pad):min(len(text), end + pad)].split())


def sentence_before(text: str, pos: int, limit: int = 240) -> str:
    """
    The fragment of the sentence running up to `pos`.

    Used to test whether a match sits inside a negation without letting the
    previous sentence's wording carry over. Deliberately does not break on a
    colon or a single newline: "Limitations:\\nrepeat expansion testing was not
    performed" is one statement laid out over two lines, and the word that makes
    it a negation is on the first of them.
    """
    chunk = text[max(0, pos - limit):pos]
    return re.split(r"(?<=[.;])\s|\n[ \t]*\n", chunk)[-1]


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


def classify_dates(text: str) -> tuple[list[str], list[str], list[str]]:
    """
    Split the dates in a document into (report-labelled, birth/collection, unlabelled).

    The first date on a report is usually the date of birth. Taking it as the
    report date inverts the staleness judgement in SKILL.md Step 5 — an eight
    year old "report" that is actually two years old, or the reverse — so the
    label preceding each date decides which bucket it lands in.
    """
    labelled: list[str] = []
    excluded: list[str] = []
    unlabelled: list[str] = []
    for m in DATE.finditer(text):
        prefix = text[max(0, m.start() - 48):m.start()]
        if REPORT_DATE_LABEL.search(prefix):
            labelled.append(m.group(0))
        elif NON_REPORT_DATE_LABEL.search(prefix):
            excluded.append(m.group(0))
        else:
            unlabelled.append(m.group(0))
    return labelled, excluded, unlabelled


def parse_variants(text: str) -> list[Variant]:
    """
    Segment the document into one block per variant before extracting fields.

    Without segmentation, a fixed-width context window pulls the neighbouring
    variant's zygosity, classification, and protein change into the wrong
    record — which is worse than missing them, because it looks correct.

    Each block runs from the end of the previous HGVS match to the start of the
    next one. Within a block: gene and transcript are read backwards from the
    variant (they precede it in report layout); classification, zygosity,
    inheritance and the protein change are read forwards, then backwards as a
    flagged fallback for column layouts, where the classification and zygosity
    columns sit to the LEFT of the variant column.
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

        if not v.classification:
            v.classification = find_last(before, CLASSIFICATIONS)
            if v.classification:
                v.needs_review.append(
                    f"classification '{v.classification}' read from text BEFORE the variant "
                    "(column layout) — confirm it belongs to this row and not to prose"
                )
        if not v.zygosity:
            v.zygosity = find_last(before, ZYGOSITY)
            if v.zygosity:
                v.needs_review.append(
                    f"zygosity '{v.zygosity}' read from text BEFORE the variant "
                    "(column layout) — confirm it belongs to this row"
                )

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
    cnvs: list[CopyNumberVariant] = []
    for m in CNV.finditer(text):
        ctx = window(text, m.start(), m.end())
        start = int(m.group("start").replace(",", ""))
        end = int(m.group("end").replace(",", ""))
        copies = int(m.group("copies"))
        cnv = CopyNumberVariant(
            band=m.group("band"),
            build=m.group("build"),
            start=start,
            end=end,
            copies=copies,
            kind="deletion" if copies < 2 else "duplication" if copies > 2 else None,
            size_bp=abs(end - start),
            classification=find_first(ctx, CLASSIFICATIONS),
            provenance="ISCN notation",
            raw_context=ctx,
        )
        if not m.group("build"):
            cnv.needs_review.append(
                "no genome build stated — GRCh37 and GRCh38 coordinates differ, "
                "and a mismatch breaks recurrent-region matching"
            )
        cnvs.append(cnv)

    cnvs.extend(parse_prose_cnvs(text, iscn_bands=[c.band for c in cnvs if c.band]))
    return cnvs


def same_region(a: str | None, b: str | None) -> bool:
    """
    Whether two cytoband strings refer to the same region.

    One report sentence routinely names a region twice at different precision —
    "a 2.6 Mb deletion at 22q11.21 … the recurrent 22q11.2 deletion" — and two
    records for one finding would read as two findings.
    """
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    return a.startswith(b) or b.startswith(a)


def parse_prose_cnvs(text: str, iscn_bands: list[str]) -> list[CopyNumberVariant]:
    """
    Pick up copy-number statements written as prose rather than ISCN.

    Copy number is deliberately left null here: "deletion" in prose does not
    distinguish a heterozygous from a homozygous loss, and asserting `copies`
    from a word would be exactly the kind of quiet wrong answer this parser is
    built to avoid. `kind` is enough to route to gene_lookup.py --cnv.
    """
    candidates: list[CopyNumberVariant] = []

    for pattern in (CNV_PROSE_SIZE_FIRST, CNV_PROSE_BAND_FIRST, CNV_PROSE_KIND_FIRST):
        for m in pattern.finditer(text):
            if CNV_REFERENTIAL.search(text[max(0, m.start() - 40):m.start()]):
                continue  # describing another region, not reporting this one
            band = m.group("band")
            kind = m.group("kind").lower()
            kind = "deletion" if kind in ("deletion", "microdeletion", "loss") else "duplication"

            size_bp = None
            groups = m.groupdict()
            if groups.get("size"):
                unit = (groups.get("unit") or "bp").lower()
                factor = {"bp": 1, "kb": 1_000, "mb": 1_000_000}[unit]
                size_bp = int(float(groups["size"]) * factor)

            ctx = window(text, m.start(), m.end())
            candidates.append(
                CopyNumberVariant(
                    band=band,
                    kind=kind,
                    size_bp=size_bp,
                    classification=find_first(ctx, CLASSIFICATIONS),
                    provenance="prose description",
                    raw_context=ctx,
                    needs_review=[
                        "read from prose, not ISCN notation — copy number and coordinates "
                        "were not stated; confirm against the cytogenetics section"
                    ],
                )
            )

    # Prefer the most precise band, and the record that carries a size with it.
    candidates.sort(key=lambda c: (-len(c.band or ""), c.size_bp is None))

    kept: list[CopyNumberVariant] = []
    for c in candidates:
        if any(same_region(c.band, b) for b in iscn_bands):
            continue  # the ISCN record for this region is authoritative
        if any(k.kind == c.kind and same_region(k.band, c.band) for k in kept):
            continue
        kept.append(c)
    return kept


def parse_repeats(text: str) -> list[RepeatExpansion]:
    """
    Extract repeat-expansion results, which the HGVS patterns cannot see.

    This matters most for FMR1: repeat sizing is a separate assay, a negative
    exome does not exclude Fragile X, and a report that contains only a repeat
    result would otherwise come back as "no variants detected" — the most
    misleading output this parser could produce.

    Sizes are reported, never interpreted. Category thresholds are gene- and
    assay-specific and belong to the source.

    Cues inside a negation are dropped before clustering, so that a limitations
    paragraph cannot manufacture a repeat result — nor suppress the "nothing
    detected" warning by making this list non-empty.
    """
    cues = [
        m for m in REPEAT_CUE.finditer(text)
        if not REPEAT_NEGATED.search(sentence_before(text, m.start()))
    ]
    if not cues:
        return []

    # Group cues that sit close together — one result section, not one per phrase.
    clusters: list[list[int]] = []
    for m in cues:
        if clusters and m.start() - clusters[-1][1] < 400:
            clusters[-1][1] = m.end()
        else:
            clusters.append([m.start(), m.end()])

    repeats: list[RepeatExpansion] = []
    for start, end in clusters:
        ctx = window(text, start, end, pad=260)
        gene, provenance = resolve_gene(text[:start], None)

        sizes: list[int] = []
        alleles = REPEAT_ALLELES.search(ctx)
        if alleles:
            sizes = [int(alleles.group("a")), int(alleles.group("b"))]
        else:
            sizes = [int(c.group("n")) for c in REPEAT_COUNT.finditer(ctx)]
        sizes = sorted(dict.fromkeys(sizes))[:4]

        motif = None
        for m in REPEAT_CUE.finditer(text[start:end + 1]):
            motif = m.group("motif") or m.group("motif2")
            if motif:
                motif = motif.upper()
                break

        r = RepeatExpansion(
            gene=gene,
            motif=motif,
            allele_sizes=sizes,
            category=find_first(ctx, REPEAT_CATEGORIES),
            methylation=(
                find_first(ctx, METHYLATION_SPECIFIC)
                or ("methylation assessed — read the source" if METHYLATION_GENERIC.search(ctx) else None)
            ),
            raw_context=ctx,
            needs_review=[
                "repeat size thresholds are gene- and assay-specific — do not interpret "
                "a repeat number without the reporting laboratory's own ranges"
            ],
        )
        if provenance in ("inferred from surrounding text", "not found"):
            r.needs_review.append(
                "gene for this repeat result was not read from a label — verify against source"
            )
        if not sizes:
            r.needs_review.append("no repeat size found — read the source")
        repeats.append(r)

    return repeats


# --------------------------------------------------------------------------
# VCF
# --------------------------------------------------------------------------

# SnpEff ANN field order is fixed by its specification.
ANN_GENE, ANN_FEATURE, ANN_HGVS_C, ANN_HGVS_P = 3, 6, 9, 10

MAX_VCF_RECORDS = 200

# A VCF is recognised by its content, never its extension. Several platforms
# refuse .vcf uploads, so these arrive renamed to .txt or pasted in whole — and
# a paste often loses the `##fileformat` line, leaving `#CHROM` as the only
# marker. Without this, such a file falls through to the prose parser, which
# picks HGVS out of the ANN= field and looks like it worked while silently
# dropping zygosity, the CLNSIG classification, the homozygous-reference
# exclusion, and the warning that a VCF carries no interpretation.
VCF_FILEFORMAT = re.compile(r"^##fileformat=VCF", re.MULTILINE)
VCF_COLUMN_HEADER = re.compile(r"^#CHROM\s+POS\s+ID\s+REF\s+ALT", re.MULTILINE)


def looks_like_vcf(text: str) -> bool:
    head = text[:8000]
    return bool(VCF_FILEFORMAT.search(head) or VCF_COLUMN_HEADER.search(head))


# Genotype call status. `reference` is the one that matters most: a 0/0 row
# means the sample does NOT carry that variant, and emitting it as a finding
# manufactures a result the person does not have — which, for a stop-gained in
# a tumour-predisposition gene, routes to real Tier 1 surveillance.
GT_CARRIED, GT_REFERENCE, GT_NOCALL, GT_UNKNOWN = "carried", "reference", "no-call", "unknown"


def interpret_gt(gt: str, chrom: str) -> tuple[str, str | None]:
    """Return (call status, zygosity). Zygosity is only meaningful when carried."""
    alleles = [a for a in re.split(r"[/|]", gt) if a]
    if not alleles:
        return GT_UNKNOWN, None
    if all(a == "." for a in alleles):
        return GT_NOCALL, None
    if any(a == "." for a in alleles):
        return GT_UNKNOWN, None  # partially called, e.g. ./1
    if all(a == "0" for a in alleles):
        return GT_REFERENCE, None
    if len(alleles) == 1:
        return GT_CARRIED, "hemizygous" if chrom.upper().removeprefix("CHR") in {"X", "Y"} else None
    if len(set(alleles)) == 1:
        return GT_CARRIED, "homozygous"
    if "0" in alleles:
        return GT_CARRIED, "heterozygous"
    return GT_CARRIED, "compound heterozygous"  # two different alt alleles, e.g. 1/2


def parse_vcf(text: str, source: str | None = None, sample: str | None = None) -> ReportRecord:
    """
    Parse a VCF into the same record shape.

    A VCF is not a clinical report: unless it carries VEP/SnpEff annotation it
    has no gene symbol, no HGVS and no classification, and even annotated it has
    no interpretation. That gap is stated in `warnings` rather than papered over.

    Which sample column is read is stated too. A trio VCF is not reliably
    proband-first — samples are as often alphabetical — so reading column 10 and
    saying nothing reports one family member's genotypes under another's name.
    """
    rec = ReportRecord(source_file=source)
    csq_fields: list[str] | None = None
    sample_names: list[str] = []
    sample_index = 0
    unannotated = 0
    reference_calls = 0
    detabbed = 0
    csq_header_missing = 0

    for line in text.splitlines():
        if line.startswith("##"):
            if "ID=CSQ" in line and "Format:" in line:
                fmt = line.split("Format:", 1)[1].strip().rstrip('">')
                csq_fields = [f.strip() for f in fmt.split("|")]
            continue
        if line.startswith("#CHROM"):
            sample_names = line.rstrip("\n").split("\t")[9:]
            if sample:
                if sample in sample_names:
                    sample_index = sample_names.index(sample)
                else:
                    rec.warnings.append(
                        f"Requested sample '{sample}' is not in this VCF. Samples present: "
                        + ", ".join(sample_names) + ". No genotypes were read."
                    )
                    sample_index = -1
            continue
        if line.startswith("#") or not line.strip():
            continue

        cols = line.rstrip("\n").split("\t")
        if len(cols) < 8 and len(line.split()) >= 8:
            # Tabs turn into spaces when a VCF is pasted into a text file or
            # through a rich-text field. VCF fields contain no spaces, so
            # splitting on whitespace recovers the row rather than dropping it.
            cols = line.split()
            detabbed += 1
        if len(cols) < 8:
            continue
        if len(rec.variants) >= MAX_VCF_RECORDS:
            rec.warnings.append(
                f"Stopped after {MAX_VCF_RECORDS} records. This looks like an unfiltered "
                "VCF rather than a reported result set — work from the lab's report."
            )
            break

        chrom, pos, _id, ref, alt, _qual, _filt, info = cols[:8]
        info_map = dict(
            (kv.split("=", 1) + [""])[:2] if "=" in kv else (kv, "")
            for kv in info.split(";") if kv
        )

        v = Variant(genomic=f"{chrom}:{pos}{ref}>{alt}")

        ann = info_map.get("ANN") or info_map.get("EFF")
        csq = info_map.get("CSQ")
        if csq and not csq_fields:
            # VEP writes CSQ field order into ##INFO=<ID=CSQ,...Format: ...>.
            # Strip the ## headers — as pasting into a text file often does —
            # and the annotation becomes undecodable: the values are all still
            # there, but nothing says which is the gene. SnpEff's ANN survives
            # the same treatment because its field order is fixed by spec.
            csq_header_missing += 1
        if ann:
            fields = ann.split(",")[0].split("|")
            if len(fields) > ANN_HGVS_P:
                v.gene = fields[ANN_GENE].upper() or None
                v.transcript = fields[ANN_FEATURE] or None
                v.hgvs_c = fields[ANN_HGVS_C] or None
                v.hgvs_p = fields[ANN_HGVS_P] or None
        elif csq and csq_fields:
            values = csq.split(",")[0].split("|")
            picked = dict(zip(csq_fields, values))
            v.gene = (picked.get("SYMBOL") or "").upper() or None
            v.transcript = picked.get("Feature") or None
            hgvs_c = picked.get("HGVSc") or ""
            hgvs_p = picked.get("HGVSp") or ""
            v.hgvs_c = hgvs_c.split(":")[-1] or None
            v.hgvs_p = hgvs_p.split(":")[-1] or None
            if hgvs_c and ":" in hgvs_c and not v.transcript:
                v.transcript = hgvs_c.split(":")[0]

        clnsig = info_map.get("CLNSIG")
        if clnsig:
            v.classification = find_first(clnsig.replace("_", " "), CLASSIFICATIONS)

        status = GT_UNKNOWN
        col = 9 + sample_index
        if sample_index >= 0 and len(cols) > col:
            keys = cols[8].split(":")
            if "GT" in keys:
                values = cols[col].split(":")
                idx = keys.index("GT")
                if idx < len(values):
                    status, v.zygosity = interpret_gt(values[idx], chrom)

        if status == GT_REFERENCE:
            # The sample does not carry this variant. Not a finding.
            reference_calls += 1
            continue
        if status == GT_NOCALL:
            v.needs_review.append(
                "genotype not called in this sample — the variant may or may not be "
                "present; this record establishes neither"
            )

        if not v.gene:
            unannotated += 1
            v.needs_review.append(
                "no gene annotation on this VCF record — annotate (VEP/SnpEff) or work "
                "from the laboratory report"
            )
        if not v.classification:
            v.needs_review.append("no classification in this VCF — a VCF does not carry one")
        if not v.zygosity and status == GT_UNKNOWN:
            # Only when the genotype was genuinely unreadable. A no-call already
            # carries its own, more accurate note.
            v.needs_review.append("zygosity not derivable — no usable GT field for this sample")

        v.raw_context = " ".join(line.split())[:400]
        rec.variants.append(v)

    rec.warnings.append(
        "Input was a VCF. A VCF carries no interpretation: classification, inheritance, "
        "phenotype and secondary-finding status live in the laboratory's report, not here. "
        "Ask for the report before writing anything clinical."
    )
    if len(sample_names) > 1 and sample_index >= 0:
        rec.warnings.append(
            f"This VCF has {len(sample_names)} samples ({', '.join(sample_names)}). "
            f"Genotypes were read from '{sample_names[sample_index]}'. Confirm that is the "
            "individual the report concerns — sample order is a convention, not a rule. "
            "Use --sample NAME to choose another."
        )
    if csq_header_missing:
        rec.warnings.append(
            f"{csq_header_missing} record(s) carry VEP CSQ annotation whose format header "
            "(##INFO=<ID=CSQ,...Format: ...>) is missing, so gene and HGVS could not be "
            "read — the values are present but nothing states their order. This is what "
            "stripping the ## header lines costs. Ask for the original file, or for that "
            "one header line."
        )
    if detabbed:
        rec.warnings.append(
            f"{detabbed} row(s) were tab-free and had to be split on spaces — this file "
            "has been through a conversion that lost its tabs. Fields containing spaces "
            "would be mis-split; check the output against the original."
        )
    if reference_calls:
        rec.warnings.append(
            f"{reference_calls} record(s) were homozygous reference in the sample read "
            "and were excluded — the sample does not carry those variants."
        )
    if unannotated:
        rec.warnings.append(
            f"{unannotated} record(s) had no gene annotation — gene, HGVS and consequence "
            "could not be derived."
        )
    if not rec.variants:
        rec.warnings.append("No VCF data lines found with a variant carried by this sample.")

    return rec


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def parse(text: str, source: str | None = None) -> ReportRecord:
    rec = ReportRecord(source_file=source)

    rec.test_type = find_first(text, TEST_TYPES)
    rec.variants = parse_variants(text)
    rec.cnvs = parse_cnvs(text)
    rec.repeats = parse_repeats(text)

    lowered = text.lower()
    rec.secondary_findings_mentioned = any(cue in lowered for cue in SECONDARY_FINDING_CUES)

    labelled, excluded, unlabelled = classify_dates(text)
    # Birth and collection dates are identifiers as well as wrong answers, so
    # they are dropped rather than offered as candidates.
    rec.candidate_dates = list(dict.fromkeys(labelled + unlabelled))[:6]
    if labelled:
        rec.report_date = labelled[0]
        rec.report_date_provenance = "labelled report-date field"
    elif unlabelled:
        rec.report_date = unlabelled[0]
        rec.report_date_provenance = "unlabelled date — first in document, not verified"
        rec.warnings.append(
            "Report date was not labelled. The date shown is the first unlabelled date in "
            "the document and may be something else entirely. Confirm it before judging "
            "whether the report is stale."
        )
    else:
        rec.report_date_provenance = "not found"

    if excluded:
        rec.warnings.append(
            f"{len(excluded)} date(s) labelled as birth or collection dates were excluded "
            "from this output as identifiers."
        )

    return finalise_warnings(rec)


def finalise_warnings(rec: ReportRecord) -> ReportRecord:
    if not rec.variants and not rec.cnvs and not rec.repeats:
        rec.warnings.append(
            "No variants, CNVs or repeat expansions detected. The report may be negative, "
            "may be an image requiring OCR, or may use a format this parser does not "
            "recognise. Read it directly."
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
    if any("read from text BEFORE" in w for v in rec.variants for w in v.needs_review):
        rec.warnings.append(
            "At least one classification or zygosity was read from text preceding its "
            "variant (column layout). Check each against the source row."
        )
    if rec.repeats and any(
        (r.gene or "").upper() == "FMR1" or (r.motif or "") == "CGG" for r in rec.repeats
    ):
        rec.warnings.append(
            "Repeat expansion result present. Repeat sizing is a separate assay from "
            "sequencing — see the FMR1 trap in references/gene_index.md."
        )
    return rec


def parse_text(text: str, source: str | None = None, do_redact: bool = True,
               sample: str | None = None) -> ReportRecord:
    """Redact first, then parse — see `redact` for why the order matters."""
    if do_redact:
        text = redact(text)
    if looks_like_vcf(text):
        return finalise_warnings(parse_vcf(text, source=source, sample=sample))
    return parse(text, source=source)


def parse_path(path: Path, do_redact: bool = True, sample: str | None = None) -> ReportRecord:
    return parse_text(read_text(path), source=str(path), do_redact=do_redact, sample=sample)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="Report file (.pdf, .txt, .vcf)")
    ap.add_argument("--text", help="Parse a literal string instead of a file")
    ap.add_argument("--json", help="Write JSON to this path instead of stdout")
    ap.add_argument(
        "--sample",
        help="VCF only: which sample column to read genotypes from (default: the first)",
    )
    ap.add_argument(
        "--no-redact", action="store_true",
        help="Keep identifiers in the output (debugging synthetic reports only)",
    )
    args = ap.parse_args()

    do_redact = not args.no_redact

    if args.text:
        record = parse_text(args.text, source=None, do_redact=do_redact, sample=args.sample)
    elif args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"error: {path} not found", file=sys.stderr)
            return 1
        record = parse_path(path, do_redact=do_redact, sample=args.sample)
    else:
        ap.error("provide a file path or --text")
        return 2

    payload = json.dumps(asdict(record), indent=2)
    if args.json:
        Path(args.json).write_text(payload)
        print(f"wrote {args.json}")
        if args.no_redact:
            print(
                "warning: --no-redact was used, so this file may contain identifiers.",
                file=sys.stderr,
            )
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
