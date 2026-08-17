# Autism Gene-to-Care Navigator (v1)

An agent skill that turns a genetic test report for autism or another neurodevelopmental
condition into two things a person can actually use: a plain-language explanation, and
the **published, actionable care implications** of what was found.

---

## Why this exists

Around **11.3%** of people evaluated for autism or a neurodevelopmental disorder receive
guideline-concordant genetic testing ([Arcebido et al., *Autism*, 2025](https://journals.sagepub.com/doi/10.1177/13623613241289980),
7,539 EHRs) — and the barriers were insurance status and race, not clinical need.

Among those who *do* get tested, the published care implications routinely never reach
them. A child with a pathogenic `PTEN` variant needs thyroid surveillance from childhood.
A `SCN2A` variant's direction of effect changes which seizure medication works —
gain-of-function showed **94%** good-to-excellent phenytoin response, loss-of-function
**0%** ([*Brain*, 2024](https://academic.oup.com/brain/article/147/8/2761/7656659)).
Families are told about the developmental gene and hear nothing about either.

**This tool is addressing the delivery of information, not the methodology.**

### What it is not

It is *not* a diagnostic classifier, and it does *not* diagnose autism. *Please seek
professionals if you have any concerns.* Autistic adults rank genetics research 23rd of 25
priorities and causation research dead last ([Cage et al., *Autism*, 2024](https://journals.sagepub.com/doi/10.1177/13623613231222656)).
The care implications handled here are **co-occurring medical conditions** — cancer risk,
epilepsy, cardiac issues — not autism itself. The skill enforces that line in its tone rules.

---

## The one rule that shapes everything

> **Never recite medical specifics from memory.**

Surveillance ages, intervals, modalities and risk percentages drift between guideline
versions. A thyroid ultrasound starting at age 7 versus age 10 is the difference between
useful and harmful — and a family *will* act on a number the tool gives them.

So the curated index records **that** a protocol exists, **which** document holds it, and
**which domains** it covers, and deliberately contains no ages, intervals or doses. The
agent fetches the source and quotes it with a retrieval date. If it cannot reach the
source, it names the document and stops.

---

## Workflow

![Workflow](docs/workflow.png)

Mermaid source: [`docs/workflow.mmd`](docs/workflow.mmd)

The **scripts form the data spine**; the **reference files govern judgement**. Scripts
move and shape data — they never make a clinical call.

| Step | Script | Governed by | Produces |
|---|---|---|---|
| 1 · Ingest | `parse_report.py` | `report_parsing.md` | Findings JSON |
| 2 · Lookup | `gene_lookup.py` + `gene_index.json` | `gene_index.md` | Sources to fetch, tier-split domains, traps |
| 2b · Fetch | *(agent, via web)* | — | Current specifics + retrieval date |
| 3 · Risk layer | *(agent)* | `risk_layer_policy.md` | Tier assignment |
| 4 · VUS | *(agent)* | `vus_communication.md` | Uncertainty framing |
| 5 · Staleness | *(agent)* | `SKILL.md` | Reanalysis prompt |
| 6 · Render | `render_brief.py` | `output_templates.md` | `brief.md`, both registers |

---

## The risk layer

The most valuable and highest-risk part of the skill. One question governs it:

> **Is there a published protocol or guideline that defines an action?**

![Risk layer decision flow](docs/risk_layer.png)

| | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| **Test** | Published protocol with a defined action | Documented elevated risk, no protocol | Neither |
| **Action** | Include prominently | Include, framed as awareness | **Exclude entirely** |
| **Examples** | PTEN thyroid/renal · TSC renal/SEGA · NF1 optic glioma · 22q11.2 cardiac/immune/calcium | Phelan-McDermid regression/catatonia · 22q11.2 psychiatric risk | Polygenic scores · risk inferred from a VUS · trajectory predictions |
| **Framing** | "Standard care, not prediction" | "More common, not inevitable, treatable" | — |
| **Percentages** | Only if retrieved this session | Only if retrieved this session | Never |

Two gates sit in front of the tiering:

- **Secondary findings** (ACMG SF v3.3) → flag and route to genetic counselling. Never
  counsel directly; these carry whole-family implications.
- **Minors** → adult-onset information is withheld *unless there is action to take in
  childhood*. This is why PTEN and TSC surveillance still goes in: it starts in childhood.

A VUS bypasses the risk layer entirely — it carries no risk information, must not drive
surveillance, and must not drive cascade testing.

---

## Repository layout

```
gene-to-care-navigator/
├── SKILL.md                    # trigger description, workflow, guardrails, tone
├── LICENSE·LICENSE-DOCS·NOTICE # Apache 2.0 for code, CC BY 4.0 for content
├── assets/gene_index.json      # 27 genes + 5 CNV regions — routing only, no specifics
├── references/                 # the judgement layer, as prose the agent reads:
│                               #   gene_index · risk_layer_policy · vus_communication
│                               #   report_parsing · output_templates
├── scripts/
│   ├── phi.py                  # identifier ruleset, shared by the two below
│   ├── parse_report.py         # report → findings JSON, identifiers redacted
│   ├── gene_lookup.py          # gene / syndrome / cytoband → sources, domains, traps
│   └── render_brief.py         # findings → two-register brief
├── tests/                      # smoke_test.py · cases.md · prompts.md ·
│   └── fixtures/               #   28 synthetic reports and VCFs — no real data
└── docs/                       # workflow + risk-layer diagrams (.png, .mmd)
```

---

## Requirements

**Python 3.10+, standard library only.** PDF input optionally uses `pdfplumber`
(`pip install -r requirements.txt`) and otherwise falls back to the `pdftotext` binary
from poppler-utils.

There is deliberately no HTTP client, LLM SDK, or bioinformatics stack — the agent does
retrieval through its own tooling. Code that touches health information is easier to audit
when there is little to audit.

---

## Scripts

Design rationale for each behaviour lives in the code comments, next to the code it
explains. Run any script with `--help` for full usage.

### `parse_report.py`

Extracts structured findings from a report — PDF, plain text, or VCF — covering sequence
variants, copy-number findings, and repeat expansions.

```bash
python scripts/parse_report.py report.pdf
python scripts/parse_report.py report.txt --json findings_raw.json
python scripts/parse_report.py annotated.vcf --sample proband
python scripts/parse_report.py --text "NM_001040142.2(SCN2A):c.5645G>A (p.Arg1882Gln), heterozygous, pathogenic"
```

It is deliberately conservative, and most of its design is about *not* asserting things
the source did not say:

- Documents are segmented into one block per variant, so a neighbouring variant's
  classification cannot be attributed to this one.
- The report date is chosen by the label in front of it. The first date on a report is
  almost always the date of birth, and taking it inverts the staleness judgement.
- Prose CNVs ("a 2.6 Mb deletion at 22q11.21") are read as well as ISCN, but `copies`
  stays null and a region named only for contrast is not counted as a finding.
- Repeat expansions are extracted separately, with sizes reported and never interpreted.
  A limitations paragraph mentioning them does not become a result.
- **A VCF is not a report.** It carries no interpretation, and says so in `warnings`.
  Homozygous-reference rows are dropped — the sample does not carry those variants — a
  no-call is flagged as establishing nothing, and the sample whose genotypes were read is
  named, because a trio VCF is not reliably proband-first.

Anything uncertain surfaces as `needs_review` on the record or `warnings` on the report.
Identifiers are redacted before parsing begins — see
[Data privacy](#data-privacy-and-confidentiality).

### `gene_lookup.py`

Routes a gene, syndrome name, alias, or cytoband to its sources and care domains.

```bash
python scripts/gene_lookup.py PTEN
python scripts/gene_lookup.py "Cowden syndrome"       # alias → PTEN
python scripts/gene_lookup.py Rett                    # syndrome name → MECP2
python scripts/gene_lookup.py 22q11.2                 # cytoband → CNV region
python scripts/gene_lookup.py --cnv 22q11.2 --copies 1
python scripts/gene_lookup.py --list
```

Returns syndrome, Tier 1 and Tier 2 domains, **sources to fetch**, traps, and patient
organisations. For an uncurated gene it returns a search order rather than nothing —
*"there is no published surveillance protocol for this gene"* is a useful answer families
rarely get. Lookups accept whichever word the person was given, since a family arrives
with "Rett" at least as often as with MECP2. CNV entries print band and copy number in
full, because deletion and duplication of one band can have partly opposite phenotypes.

### `render_brief.py`

Assembles the two-register document from a structured findings JSON.

```bash
python scripts/render_brief.py findings.json --out brief.md
python scripts/render_brief.py findings.json --family-only
```

Empty sections omit themselves. The PHI check **refuses to write the file** if it finds an
identifier — writing is the step that makes a leak durable, so that is the step that stops
— with `--allow-phi` to override deliberately. It uses `scripts/phi.py`, the same ruleset
the parser redacts with, so the two cannot drift apart.

---

## Guardrails

1. **No diagnosis, no prescription, no prognosis.** Assemble evidence; the clinical team decides.
2. **Every clinical specific carries a source and a retrieval date.**
3. **Never recite surveillance ages, intervals, or drug doses from memory.**
4. **A VUS is not actionable** — and the output says so explicitly.
5. **Secondary findings route to genetic counselling.** Never counselled directly.
6. **Abstain loudly when evidence is thin.** The FDA-cleared autism diagnostic aid Canvas Dx
   abstains on 37% of real-world cases ([*Scientific Reports*, 2025](https://www.nature.com/articles/s41598-025-15575-8)).
   Visible limits are why clinicians trust a tool.
7. **De-identify by default** — enforced in code, with limits worth knowing:
   see [Data privacy and confidentiality](#data-privacy-and-confidentiality).
8. **No unsourced risk numbers.** A remembered percentage is worse than none.

Showing the reasoning for every assertion is also what keeps this inside the 21st Century
Cures Act §3060 clinical-decision-support carve-out rather than in medical-device
territory — the clinician can independently review the basis for everything it says.

---

## Data privacy and confidentiality

A genetic test report is among the most sensitive documents a person will ever hold. It
concerns a named individual, it is frequently about a child, and it carries information
about relatives who never consented to anything. **The redaction in these scripts is a
safety net, not permission.**

### What the code does

| Where | What it does |
|---|---|
| `phi.py` | The single identifier ruleset — name, DOB, record/hospital number, NHS number, SSN-shaped strings, lab accession, email — used by both scripts below, so they cannot drift apart. |
| `parse_report.py` | Redacts every rule above from the whole document *before* parsing. `--no-redact` opts out and is for synthetic reports. |
| `parse_report.py` | Drops dates labelled as birth or collection dates — wrong answers *and* identifiers. |
| `render_brief.py` | Scans the assembled document with the same ruleset and refuses to write the file if it finds any identifier. |
| `.gitignore` | Excludes `*.vcf`, `reports/`, `patient_data/`, `findings*.json`, `brief*.md`. |
| Everywhere | No network calls carry report content. The agent fetches *guideline sources*, never anything derived from the report. |

### What it cannot do

- **Regex redaction is pattern-matching, not comprehension.** It catches labelled
  identifiers. It misses a name in running prose ("Jack's results show…"), an unlabelled
  address, a referring clinician, an unusual date format, and anything mangled by OCR.
- **De-identification is not anonymisation.** A variant is itself identifying. Genomic
  data is re-identifiable in principle, and stripping every name and number does not make
  it anonymous. Under GDPR it remains special category data (Art. 9); under HIPAA, genetic
  information is PHI and is covered by GINA. Treat parser output as identifiable health
  data however clean it looks.
- **It says nothing about where the text goes.** Running this skill puts the report's
  content into the context of whatever model runs the agent, under that provider's terms
  rather than this repository's. **That is a disclosure, and it is your decision to make,
  not the tool's.**

### If you are handling other people's reports

- **Request for lawful consent when using real data**: patient consent or another
  Art. 6/Art. 9 basis under GDPR, a BAA under HIPAA, plus whatever your institution
  requires — DPIA, IG review, ethics approval. A clinician's duty of confidence applies
  here exactly as it does to any other disclosure.
- **Work from a de-identified copy** where one can be made. Redact before the file reaches
  the parser rather than relying on the parser to redact after.
- **A child's genetic data belongs to the child**, including the parts that will matter to
  them as an adult. A parent can consent today; that does not settle what should be
  written down, retained, or shared later.
- **Do not de-identify by removing only what you can see.** Family structure, a rare
  syndrome plus a location, or a distinctive variant can identify a person alone.
- **Delete intermediates.** `findings*.json` and `brief*.md` are gitignored but still on
  disk, and they contain everything.

If it is **your own report or your child's**, it is yours to share — leave the redaction
defaults on so identifiers don't reach a file you later hand to someone else. Everything
above about where the text goes still applies.

**Nothing here is legal advice.** If real patient data is involved and you are not certain
what applies, ask your DPO, IG lead, privacy officer, or IRB.

---

## Coverage

27 genes and 5 recurrent CNV regions, chosen because published care guidance genuinely
exists — not to look comprehensive.

- **Tumour predisposition** — PTEN, TSC1/TSC2, NF1, DICER1
- **Recurrent CNVs** — 22q11.2 del, 16p11.2 del/dup, 15q11-q13 dup, 22q13 del
- **Channels / synaptic** — SCN2A, SCN1A, SCN8A, GRIN2A/2B, CACNA1C, STXBP1
- **Chromatin / scaffold** — MECP2, SHANK3, SYNGAP1, CHD8, ADNP, ARID1B, ANKRD11, DYRK1A, KMT2A, POGZ, MED13L
- **Other** — FMR1, UBE3A, NRXN1, PPP2R5D, SETD5, AUTS2

**Adding a gene:** add an entry to `assets/gene_index.json` (`syndrome`, `tier1_domains`,
`tier2_domains`, `sources`, `traps`, `organisations`; aliases use
`{"GENE2": {"same_as": "GENE1"}}`), then a matching prose section in
`references/gene_index.md`. **Do not add ages, intervals, modalities, or doses** — if you
want to, the right move is a better `sources` entry.

---

## Testing

```bash
python tests/smoke_test.py                    # parser regression + identifier leak scan
python scripts/gene_lookup.py --list          # index integrity
```

Testing splits into two layers, and only one can be automated.

**Parser layer** — `smoke_test.py` runs 28 synthetic fixtures through `parse_report.py`
and asserts what came out. Expectations were recorded from verified runs rather than
written from intent, so a failure means behaviour changed — read the diff before editing
the expectation. It also cross-checks every planted identifier against *every* fixture's
output, and refuses to pass unless each fixture carries a synthetic marker. The corpus
spans the layouts, the clinical scenarios, the VCF variants, and the cases that must
produce **nothing**; [`tests/cases.md`](tests/cases.md) lists what each one tests.

**Skill layer** — [`tests/cases.md`](tests/cases.md) carries the per-fixture rubric,
scored by hand because the failures that matter are judgement failures. Alongside it:
[`prompts.md`](tests/prompts.md) (ready-to-paste),
[`adversarial_prompts.md`](tests/adversarial_prompts.md) (guardrail pressure tests), and
[`no_trigger_prompts.md`](tests/no_trigger_prompts.md) (must-not-fire cases).

**No real patient report has been through this repository, and doing so is not a casual
step** — see [Data privacy](#data-privacy-and-confidentiality) first.

---

## Limitations

- **The gene index is a starting set**, not a reference database. Most NDD genes are not in it.
- **The parser is regex-based.** It flags rather than guesses, but check its output
  against the source; it will not handle every lab's format.
- **No OCR.** Photographed reports need OCR first, then character-by-character
  verification of the variant string. OCR also defeats identifier redaction.
- **Redaction is regex, and de-identified is not anonymous.**
  See [Data privacy](#data-privacy-and-confidentiality).
- **Direction of effect is not inferred.** For SCN2A, SCN8A, GRIN2A/2B the skill states
  that gain- versus loss-of-function is decisive and routes it to genetics. Guessing wrong
  inverts the treatment.
- **Guideline currency depends on retrieval.** If a guideline is superseded, the pointer
  needs updating.

---

## Citations

| Claim | Source |
|---|---|
| 11.31% guideline-concordant genetic testing rate | [Arcebido et al., *Autism*, 2025](https://journals.sagepub.com/doi/10.1177/13623613241289980) |
| Autistic community research priorities | [Cage et al., *Autism*, 2024](https://journals.sagepub.com/doi/10.1177/13623613231222656) |
| ES/GS as first- or second-tier testing | [Manickam et al., *Genetics in Medicine*, 2021](https://www.gimjournal.org/article/S1098-3600(21)05168-6/fulltext) |
| Secondary findings gene list | [ACMG SF v3.3, *Genetics in Medicine*, 2025](https://www.gimjournal.org/article/S1098-3600(25)00101-7/fulltext) |
| PTEN surveillance | [International PHTS Consensus, *Clin Cancer Res*, 2025](https://aacrjournals.org/clincancerres/article/31/9/1754/761247/Cancer-and-Overgrowth-Manifestations-of-PTEN) · [Pediatric update, *Clin Cancer Res*, 2025](https://aacrjournals.org/clincancerres/article/31/2/234/751094/Update-on-Pediatric-Surveillance-Recommendations) |
| 22q11.2 management | [AAP Health Supervision, *Pediatrics*, 2025;156(2)](https://publications.aap.org/pediatrics/article/156/2/e2025072717/202658/Health-Supervision-for-Children-With-22q11-2) · [Adult recommendations, *Genetics in Medicine*, 2023](https://www.gimjournal.org/article/S1098-3600(22)01028-0/fulltext) |
| SCN2A direction of effect → drug response | [*Brain*, 2024;147(8):2761](https://academic.oup.com/brain/article/147/8/2761/7656659) |
| Variant-class-dependent ASO therapy | [Kim-McManus et al., *Nature Medicine*, 2026](https://www.nature.com/articles/s41591-026-04527-y) |
| Blood RNA covers most ID/epilepsy panel genes | [De Cock et al., *npj Genomic Medicine*, 2025](https://www.nature.com/articles/s41525-025-00502-7) |
| Abstention as a trust feature | [Salomon et al., *Scientific Reports*, 2025](https://www.nature.com/articles/s41598-025-15575-8) |
| Gene discovery since 2021–22 (reanalysis rationale) | [Fu et al., *Nat Genet*, 2022](https://www.nature.com/articles/s41588-022-01104-0) · [Zhou et al., *Nat Genet*, 2022](https://www.nature.com/articles/s41588-022-01148-2) · [Trost et al., *Cell*, 2022](https://www.cell.com/cell/fulltext/S0092-8674(22)01324-1) |

---

## Roadmap

- **v1** *(current)* — report translation + gene-to-care + risk layer
- **v2** — Testing Gap Checker: what testing is guideline-indicated given a clinical
  picture, and the wording to bring to a clinician or insurer. Targets the 11.3% directly.
- **v3** — Reanalysis Advocate: which NDD genes were described since the report date, and
  a drafted request to the clinical service.
- **v4** — functional triage underneath: local SpliceAI/Pangolin, tissue-expression check
  for whether blood RNA-seq would be informative, AlphaFold structural context.

---

## Licence

Dual-licensed, because most of this repository is content rather than code.

| Path | Licence |
|---|---|
| `scripts/` | [Apache License 2.0](LICENSE) |
| `SKILL.md`, `README.md`, `references/`, `assets/gene_index.json`, `docs/` | [CC BY 4.0](LICENSE-DOCS) |

**Why the split.** The Python files are small; the substance here is curated prose and a
curated dataset. CC BY 4.0 expressly covers *sui generis* database rights (§4 of its legal
code), which matters for `gene_index.json` in jurisdictions that treat database rights
separately from copyright.

**If you modify the clinical content**, CC BY 4.0 §3(a)(1)(B) requires you to indicate
that you changed it. For `references/risk_layer_policy.md` and
`references/vus_communication.md`, make it prominent — they encode the guardrails, and
downstream users need to know they are not running the reviewed version.

**Third-party content.** No text from clinical guidelines, GeneReviews, or other
copyrighted sources is reproduced here. The gene index records factual identifiers only —
symbols, syndrome names, care-domain labels, citations, URLs — and excludes screening
ages, intervals, modalities and doses by design. That exclusion exists for clinical safety
and keeps the repository clear of third-party copyright. Please preserve it.

See [`NOTICE`](NOTICE) for attribution requirements and the full disclaimer.

---

## Disclaimer

This software summarises published information. **It is not a medical device, does not
provide medical advice, and does not make diagnoses.** Output is intended to support
conversations with qualified clinicians, not replace them. Every clinical decision belongs
to the person's clinical team.

The warranty disclaimers in Apache 2.0 and CC BY 4.0 concern the software and content as
such. They are not protection against harms arising from clinical use. Anyone deploying
this in or near a clinical setting should obtain independent legal and regulatory advice.
