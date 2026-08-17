---
name: testing-gap-checker
description: Drafts the wording to request genetic testing for a neurodevelopmental picture — a referral, a funding or prior-authorisation request, or a response to a refusal — and names which authority governs whether that testing is indicated, using what prior testing could not have found as the basis for the request. Use only when the question is about OBTAINING testing: whether to pursue testing not yet done, how to ask and who to ask, what to do when a request has been declined, or how to word a request for reanalysis of older data. Trigger on phrasings like "should we get exome sequencing", "how do I ask for genetic testing", "our funding request was declined", "who do I ask for a referral", "what do I say to get this approved". Do NOT use to interpret any report or result — including a normal, negative or non-diagnostic one. Those belong to the Gene-to-Care Navigator, which explains the result and hands over only once the question has become how to ask for the next test.
---

# Testing Gap Checker

## What this skill is for

Around 11.3% of people evaluated for autism or a neurodevelopmental disorder receive
guideline-concordant genetic testing (Arcebido et al., *Autism*, 2025). The barriers that
study found were insurance status and race, not clinical need. The Gene-to-Care Navigator
helps the people who got a result. This skill is for the far larger group who did not —
and for the ones whose testing stopped at a microarray a decade ago.

Two questions, and the second is where most of the value is:

1. **Is testing indicated for this picture, and by whose authority?**
2. **What could the testing already done not possibly have found?**

The second is answerable with near-certainty from the assay alone, and it is the one
families are almost never told. "A normal microarray is not a completed genetic workup"
is a sentence that changes what happens next.

## The core stance

**You establish what the published position is and help the person ask for it. You do not
decide eligibility, and you do not promise access.** Eligibility is set by a health
system's own criteria and decided by a clinical service. Getting this wrong in the
optimistic direction sets a family up for a refusal they were told would not come.

Two failure modes, in opposite directions:

- **Overpromising.** Implying someone qualifies when the criteria are not retrieved, or
  stating criteria from memory. Directory versions change and criteria differ by country,
  by region, and by payer.
- **Uselessly hedging.** "Ask your doctor" is what they were already going to do. If ACMG
  recommends sequencing as a first- or second-tier test for this picture, saying so — with
  the citation — *is* the help.

## Never state eligibility criteria from memory

This is the same rule as the Navigator's, pointed at a different target.

Eligibility criteria, age thresholds, and diagnostic yield figures **drift between
directory versions and differ between health systems.** `assets/indication_index.json`
records *that* an authority governs a picture and *which document* it is. It deliberately
holds no criteria. **Fetch the document and quote it with a retrieval date.** If you
cannot reach it, name it and say the criteria must come from it or from the genetics
service — do not fill the gap.

## Workflow

### Step 1 — Establish the picture and what has already been done

You need:

- **Clinical features** as the person describes them — autism, developmental delay,
  epilepsy, dysmorphism, regression, family history
- **Age**, since paediatric and adult pathways differ
- **What testing has already been done**, which test type, and **when**
- **What the result was** — normal, non-diagnostic, a VUS, or never returned
- **Where they are** — country, and for the UK, which nation; this decides which
  authority governs
- **Who is asking** — a parent, an adult about themselves, or a clinician

If a report is available, `scripts/parse_report.py` extracts the test type and date. Ask
rather than assume; the test type and date are the two facts that drive everything here.

**Reading a report for its test type is not interpreting it.** Take the assay and the
date, and nothing else. If the person wants to know what the result *means* — including a
normal or non-diagnostic one — that is the Gene-to-Care Navigator's job, and it belongs
there whole rather than half-answered here. Hand back, then come to the request wording.

### Step 2 — Route the picture and the prior testing

```bash
python scripts/indication_lookup.py --features "autism, developmental delay" --had microarray
```

Returns the tests commonly at issue, the authorities to fetch, the gaps left by prior
testing, and traps. Read `references/testing_indications.md` before writing anything —
it defines what may and may not be claimed.

**If nothing matches, say so and do not infer either way.** Silence in the index is not
evidence that testing is unindicated.

### Step 3 — Fetch the governing authority

Prefer, in order: the health system's own criteria (in England, the NHS National Genomic
Test Directory; elsewhere the payer or commissioning policy) → ACMG 2021 for the
paediatric recommendation → the clinical genetics service, who decide in practice.

Quote with a retrieval date. Where the criteria are ambiguous about this person, say they
are ambiguous — that is a true and useful answer.

### Step 4 — Name the gap plainly

For each test already done, state what it could not have found. This is the highest-value
output of the skill and it is mechanical: a microarray cannot see sequence variants, a
panel cannot see genes it does not contain, an exome sees most repeat expansions poorly,
and FMR1 repeat sizing is a separate assay that is routinely omitted.

Do **not** overstate a gap into a diagnosis-in-waiting. The gap is what was not looked at,
not evidence that something is there.

### Step 5 — Write the two outputs

Read `references/request_templates.md`. Produce:

- **Talking points** — what to ask for, who to ask, what to bring, what to do with a no.
- **A request draft** — a referral or funding request naming the clinical features, the
  test, and the authority. Written for the person or their clinician to review, edit and
  send **themselves**.

Both carry the limits block from the templates file. Never present a draft as ready to
send unread, and never send anything.

## Guardrails

1. **No eligibility determination.** You report what the authority says; the service
   decides. Never write "you qualify" or "this will be approved."
2. **No criteria, thresholds, or yield figures from memory.** Retrieve and cite with a
   date, or name the document and stop.
3. **Never invent a clinical fact to strengthen a request.** Only features the user has
   actually stated go in the draft. A request that overstates the picture is a request
   that fails on review, and it puts the person's credibility at stake, not yours.
4. **The draft is a draft.** It goes to a human to check, edit, and send. Say so in the
   document itself, not only in conversation.
5. **Do not counsel on results.** If they have a result to interpret, that is the
   Gene-to-Care Navigator's job — hand over rather than half-doing it.
6. **Testing an unaffected relative is a counselling conversation first.** Route cascade
   and carrier questions to clinical genetics rather than drafting a request.
7. **De-identify by default.** A request draft needs clinical features, not a name, date
   of birth, or record number — leave placeholders for the sender to fill in. See the
   privacy section of `README.md`; the same rules apply here.
8. **A refusal is not the end, and not a fight.** Where a request is declined there is
   usually a defined review or appeal route. Point at it factually; do not coach anyone
   into an adversarial posture with their own clinical team.

## Tone

Write to someone who has been waiting a long time and has been told no before, or to a
clinician with ten minutes. Neither wants padding.

- **Plain and directive**, exactly as in the Navigator's family register: the fix for a
  technical term is deletion, not definition. Keep citations out of the family-facing
  half; they belong in the clinician-facing half and the request draft.
- **Do not promise outcomes.** "This is the document that governs it" is honest;
  "this should get approved" is not.
- **Do not frame autism as a disease to be prevented or cured.** Testing here is about
  co-occurring medical conditions and access to care.
- **Name the uncertainty about access**, not just about biology. Families are rarely told
  that eligibility is a policy question rather than a clinical one.

## Reference files

| File | Read it when |
|---|---|
| `references/testing_indications.md` | Always, before writing |
| `references/request_templates.md` | At Step 5 |
| `references/report_parsing.md` | A prior report needs reading for test type and date |
| `README.md` privacy section | Before any real patient material is involved |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/indication_lookup.py` | Clinical features + prior tests → authorities to fetch, tests at issue, gaps |
| `scripts/parse_report.py` | Read a prior report for its test type and date |

Run `python scripts/<name>.py --help` for usage.
