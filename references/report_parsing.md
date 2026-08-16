# Reading a Genetic Test Report

## What you are looking for

| Field | Why it matters | Where it usually is |
|---|---|---|
| Gene symbol | Drives everything downstream | Result / Findings section |
| Transcript (`NM_…`) | Same variant reads differently against different transcripts | Beside the gene |
| HGVS `c.` and `p.` | The variant itself | Result table |
| Classification | Whether anything is actionable | Result table, or bolded prose |
| Zygosity | Het / hom / hemizygous — changes interpretation | Result table |
| Inheritance | De novo vs inherited is major evidence | "Parental studies" or interpretation text |
| CNV coordinates + size | Recurrent-region matching | Cytogenetics section |
| Test type | What it could and couldn't have found | Methods, or the header |
| **Report date** | Staleness → reanalysis question | Header or footer |
| Indication / phenotype | Whether the finding fits | "Reason for referral" |
| Secondary findings | Special handling required | Own section, or explicitly "not analysed" |

## Test types and their blind spots

Knowing what a test **could not** have found is often the most useful thing you can tell
someone with a negative report.

- **Karyotype** — large rearrangements only. Misses almost everything relevant here.
- **FISH** — targeted; only finds what was asked for.
- **Chromosomal microarray (CMA)** — CNVs. Misses sequence variants entirely, and
  balanced rearrangements. A negative CMA is not a negative genetic workup.
- **Targeted panel** — only the genes on the panel, which was fixed at the version date.
  Ask which version. Panels age badly.
- **Exome (ES)** — coding regions. Misses deep intronic, most repeat expansions, some
  CNVs depending on the pipeline, and anything in poorly covered regions.
- **Genome (GS)** — broadest short-read coverage, but still limited for repeat expansions
  and complex structural variants.
- **Long-read GS** — better for structural and repeat variation. Long-read increased
  detection of gene-disrupting structural variants by 33% and tandem repeats by 38% over
  short-read in autism families (*Cell Genomics*, 2026). Rarely done clinically yet.

**FMR1 / Fragile X is a specific trap:** repeat expansion testing is usually a separate
assay. A negative exome does **not** rule out Fragile X. If the indication is autism/ID
and there is no separate FMR1 result, flag it.

## Classification language

Labs use ACMG/AMP five-tier terms. Map any local wording onto them:

| Report says | Read as |
|---|---|
| Pathogenic | Pathogenic |
| Likely pathogenic | Likely pathogenic (~≥90% certainty — treated as actionable) |
| Variant of uncertain significance / VUS / Class 3 | **Uncertain — not actionable** |
| Likely benign / benign | Not causative |

Watch for hedged prose like "possibly disease-associated" or "of potential clinical
relevance" that is not a formal classification. Treat those as VUS and say that you have
done so.

## HGVS quick reference

`NM_001040142.2(SCN2A):c.5645G>A (p.Arg1882Gln)`

- `NM_…` transcript with version — **check it is the clinically relevant transcript**;
  a variant numbered against a non-canonical transcript can look like a different variant
- `c.` coding DNA position
- `p.` protein consequence; `p.(...)` in brackets means predicted, not observed
- `c.5645G>A` substitution · `c.1234del` deletion · `c.1234dup` duplication ·
  `c.1234-2A>G` intronic, 2 bp before exon start — canonical splice acceptor
- `fs` frameshift · `*` or `Ter` stop · `=` no protein change (synonymous — but may still
  affect splicing)

## CNV notation

`arr[GRCh38] 22q11.21(18,924,718-21,111,383)x1`

- `x1` = one copy (deletion) · `x3` = three copies (duplication)
- Check the **genome build** — GRCh37 and GRCh38 coordinates differ; a mismatch will
  break recurrent-region matching
- Compare against recurrent regions in `gene_index.md` before treating a CNV as novel

## Practical notes

- **Photographed or scanned reports** are common from families. OCR then verify the
  variant string character by character — a misread `c.1234G>A` vs `c.1234C>A` is a
  different variant. If any character is unclear, ask rather than guess.
- **Partial reports** — families often share only the results page. If the methods and
  date are missing, ask; test type and date change the advice materially.
- **Multiple findings** — rank by classification first (P/LP before VUS), then by
  whether Tier 1 surveillance content exists. Do not bury a PTEN finding under three VUS.
- **De-identify before writing to any file.** Strip names, DOB, MRN, ordering clinician.