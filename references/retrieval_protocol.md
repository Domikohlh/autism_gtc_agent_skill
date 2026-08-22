# Retrieval Protocol

How to establish what is known about **any** gene, variant or condition — not just the
ones this repository happens to have curated.

This replaces coverage. No index can hold every gene, and one that tried would be stale
the month it shipped. What travels instead is the *method*: where to look, in what order,
what to extract, and how to know when you have not found enough.

The curated indexes are now a **pitfall registry, not a coverage claim.** A gene being
absent from them says nothing about that gene. Run this protocol either way; the registry
only tells you about traps somebody already fell into.

---

## Step 1 — Establish what you are looking up

Before searching, fix these. Guessing any of them wastes the retrieval:

- **Gene symbol** (HGNC-approved) or **cytoband** or **syndrome name**
- **Variant**, if there is one: transcript, HGVS, classification, zygosity
- **The clinical question** — surveillance? medication? prognosis? access to testing?
- **Who is asking**, and for whom. A parent, an adult about themselves, a clinician
- **Age band**, because paediatric and adult guidance diverge and disclosure rules differ

---

## Step 2 — Retrieve, in this order

Stop as soon as you have an authoritative answer. Later sources are fallbacks, not
supplements to stack up.

| Order | Source | What it is good for | Note |
|---|---|---|---|
| 1 | **A named guideline or consensus statement** for the condition | Surveillance, management, medication | The strongest thing you can cite. Named body, year, retrieval date |
| 2 | **GeneReviews** | Gene–disease association, natural history, management | Chapter-per-condition; check the revision date |
| 3 | **ClinGen** | Gene–disease validity, dosage sensitivity, actionability | Says how *established* an association is — often the honest answer |
| 4 | **ClinVar** | How the variant has been classified by others | Classifications conflict; report the spread, not one submitter |
| 5 | **OMIM** | Phenotype catalogue, allelic variants | Dense; good for confirming a syndrome name |
| 6 | **The condition's specialist body** | Practice guidance | Cancer, cardiac, metabolic and neurodevelopmental fields each have their own |
| 7 | **A patient organisation** | Family-facing material, registries, natural history studies | Often the thing families value most |
| 8 | **Recent primary literature** | Everything above came up empty | Weakest. Say so if you rely on it |

**Health-system access questions are separate** — see `testing_indications.md`. A guideline
recommending a test says nothing about whether a given person can obtain it.

---

## Step 2b — Variant-level evidence: ClinVar and OMIM

Step 2 establishes what is known about the **gene**. When the report names a specific
**variant**, there is a second question no gene-level source answers: *how well
established is this particular variant's classification, and who established it?*

Run this only when you have a variant — transcript + HGVS, or an rsID. Skip it for a
CNV band, a karyotype, or a negative report; there is nothing to look up.

### The rule this step sits under

> **The reporting laboratory's classification is the one that governs. ClinVar and OMIM
> tell you its provenance, not a different answer.**

You are not re-classifying and you cannot. You do not have the lab's evidence — their
population frequencies, the phenotype they were given, segregation in this family, any
functional work they commissioned. What you *can* establish is whether the classification
is well-supported or lonely, and how recently anyone looked. That is a **confidence**
question, and it is reported as one.

**Never promote and never downgrade.** If the report says VUS and ClinVar shows two
submitters calling it pathogenic, it is still a VUS in everything you write. Say the
classification is disputed, say who disputes it, and route it to the reporting laboratory
and the genetics team — a lab can re-issue a report, and you cannot.

### Query construction

Search, never recall. Do not write a MIM number, a Variation ID or an accession from
memory: open the search, and take the identifier off the page you actually loaded.

| Source | Search entry point |
|---|---|
| ClinVar, by HGVS | `https://www.ncbi.nlm.nih.gov/clinvar/?term=` + the URL-encoded `NM_...:c....` string |
| ClinVar, by gene + protein change | `https://www.ncbi.nlm.nih.gov/clinvar/?term=GENE%5Bgene%5D+AND+p.Arg130Ter` |
| ClinVar, all variants in the gene | `https://www.ncbi.nlm.nih.gov/clinvar/?term=GENE%5Bgene%5D` |
| ClinGen gene–disease validity and dosage | `https://search.clinicalgenome.org/kb/genes?search=GENE` |
| ClinGen Evidence Repository (expert-panel variant calls) | `https://erepo.clinicalgenome.org/evrepo/` |
| OMIM | `https://www.omim.org/search?index=entry&search=GENE` |

`scripts/gene_lookup.py GENE --variant "c.388C>T"` builds these for you and prints the
extraction shape alongside them.

**A ClinVar variant record links out to the rest.** Once you have the record it names the
OMIM allelic-variant number and the ClinGen allele ID on the page. Follow those links
rather than running a fresh search — it is one hop instead of three, and the identifier
came off a page rather than out of memory.

**OMIM often will not load for an automated fetch.** It sits behind bot verification, which
is not to be worked around. If you cannot reach it, write "not retrieved" and rely on
ClinVar, ClinGen and GeneReviews; do not fill the OMIM fields from memory, and do not
present the gap as though it were checked.

**Search the variant, never the patient.** A transcript and an HGVS string go into the
query box; a name, a date of birth, an MRN or an accession number from the report never
does. A search box is a third party.

### Extract into this shape

```
ClinVar
  Variation ID        [from the page you opened]
  Classifications     [each distinct call, with how many submitters gave it]
  Review status       [the phrase ClinVar prints, and its star count]
  Last evaluated      [date on the most recent submission]
  Conditions asserted [what submitters linked it to]
  Conflict            [yes/no — if yes, report the spread, never pick a winner]
  Submitters          [names, checked against the reporting lab — see traps]

OMIM
  Gene entry          [MIM number, off the page]
  Phenotypes          [name, MIM number, inheritance, phenotype mapping key]
  Allelic variant     [listed or not — absence means nothing]

Agreement with the report   [agrees / disputed / not present in these databases]
```

### What ClinVar's review status is worth

| Review status | Stars | What it licenses you to write |
|---|---|---|
| Practice guideline | 4 | The strongest provenance available. Name the guideline |
| Reviewed by expert panel | 3 | A ClinGen expert panel applied gene-specific criteria. Cite the panel |
| Criteria provided, multiple submitters, no conflicts | 2 | Independent labs agree. Say how many |
| Criteria provided, conflicting classifications | 1 | **Report the spread.** Do not resolve it |
| Criteria provided, single submitter | 1 | One lab's opinion — possibly the one that wrote this report |
| No assertion criteria provided | 0 | Carries no weight. Do not cite it as support |
| Not in ClinVar at all | — | Means nothing. Many pathogenic variants have never been submitted |

### Traps

- **Circularity.** The single submitter may *be* the laboratory that issued the report in
  front of you. Then ClinVar is not corroboration — it is the same opinion counted twice.
  Check submitter names against the report letterhead before calling it independent.
- **Staleness.** A 2016 submission predates the gene-specific criteria now in use. "Last
  evaluated" often matters more than the classification itself.
- **Absence is not evidence.** A variant missing from ClinVar has not been submitted. That
  is a statement about submission behaviour, not about the variant.
- **OMIM allelic variants are historical exemplars** — a curated selection illustrating the
  gene, not a classification service and not a complete list. A variant's absence from that
  section says nothing.
- **A classification is not a penetrance figure.** "Pathogenic" says the variant causes the
  condition. It says nothing about how often, in whom, at what age, or how severely. Do not
  let a strong classification licence a risk number — see `risk_layer_policy.md`.

---

## Step 3 — Extract into this shape

Fill the same fields whatever the disease, so the output is comparable and the gaps are
visible. Write "not established" rather than leaving a field blank — an empty field reads
as an oversight, "not established" is a finding.

```
Gene / region        [symbol or cytoband]
Condition            [name, and any alias families will meet]
Association strength [ClinGen validity, or how many independent reports exist]
Mechanism            [loss of function, gain of function, dosage, repeat expansion,
                      imprinting — or "not established"]
Inheritance          [as stated for the condition, not inferred from this variant]
Tier 1 domains       [organ systems with a PUBLISHED surveillance protocol + the document]
Tier 2 associations  [documented, no protocol — what to watch for, and who to tell]
Medication notes     [where a finding changes drug choice or is a contraindication]
Time-critical        [anything needing prompt clinical input — cardiac, immune, metabolic]
Organisations        [patient body, registry, natural history study]
Sources              [each with a retrieval date]
```

**Never fill a field from memory.** Ages, intervals, doses and percentages drift between
guideline versions and you will get them subtly wrong. Retrieve or write "not retrieved".

---

## Step 4 — Calibrate the abstention

The risk of a retrieval-driven approach is that search always returns *something*. Say
which of these you are in, plainly:

- **Established** — a named guideline covers this. Quote and cite it.
- **Emerging** — real gene–disease association, natural history still thin, no protocol.
  Say what is known and that no schedule exists.
- **Sparse** — a handful of case reports. Say so. Registry enrolment is often the most
  useful concrete action you can offer.
- **Nothing found** — say that. *"There is no published surveillance protocol for this
  gene"* is a real answer, and one families almost never get.

**Do not promote a level to look useful.** Sparse dressed as established is the failure
this protocol exists to prevent, and it is the same failure as reciting from memory.

---

## Step 5 — Check the registry for traps

`assets/gene_index.json` and `assets/indication_index.json` hold curated pitfalls — places
where the obvious reading is wrong. Check them **after** retrieving, not instead of:

- SCN2A, SCN8A, GRIN2A/2B — direction of effect decides the drug and cannot be read from
  the notation
- 16p11.2 — deletion and duplication have partly opposite phenotypes
- FMR1 — repeat sizing is a separate assay; a normal exome does not exclude it
- CACNA1C — cardiac conduction, time-critical
- The assay blind-spot table — disease-agnostic, and true whatever you are looking up

A gene absent from the registry has no known trap **recorded here**. That is not the same
as having none.
