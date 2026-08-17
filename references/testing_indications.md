# Testing Indications Policy

How to decide what may be claimed about whether genetic testing is indicated, and what
may not. Read before writing anything for the Testing Gap Checker.

---

## The governing distinction

Two different questions get conflated constantly, and the whole skill depends on keeping
them apart:

| | Question | Who answers it | What you may say |
|---|---|---|---|
| **Clinical** | Is testing *recommended* for this picture? | Published guidelines | Retrieve and quote the recommendation |
| **Access** | Is *this person* eligible, and will it be funded? | The health system, then the clinical service | Name the governing document. Never decide it. |

A guideline recommending exome sequencing for developmental delay does **not** mean a
given person will get it. Conflating the two produces a family who were told they
qualified, walking into a refusal. That is a worse outcome than never having asked,
because it costs trust in the clinician as well as the test.

---

## Three claim levels

Every statement about indication falls into one of these. Say which one you are in.

**Level 1 — Established recommendation.** A named guideline recommends this test for this
picture. ACMG 2021 recommending exome or genome sequencing as a first- or second-tier test
for congenital anomalies, developmental delay and intellectual disability is the canonical
example. Quote it, cite it, date it.

> "ACMG's 2021 guideline recommends exome or genome sequencing as a first- or second-tier
> test for this picture [cite, retrieved date]. That is a recommendation about clinical
> practice — whether it is funded where you are is a separate question, below."

**Level 2 — System-specific eligibility.** Whether this person meets criteria. This is a
policy question with a documented answer that you must **retrieve, not recall**. In
England the NHS National Genomic Test Directory states eligibility per indication and is
revised periodically. Elsewhere it is a payer policy or a commissioning document.

> "The criteria that decide this are in [document, version, retrieved date]. Reading them
> against what you have told me, [what they appear to say]. The genetics service makes the
> actual decision, and they may know of routes I cannot see from the document."

**Level 3 — Not established.** No recommendation you could retrieve, or criteria that do
not clearly address this picture. Say that plainly.

> "I could not find a guideline that addresses this directly. That does not mean testing
> is unreasonable to ask about — it means the case rests on clinical judgement rather than
> on a document, and the genetics service is the right place to put it."

**Never promote a claim a level** to make an answer feel more useful. A Level 2 answer
dressed as Level 1 is the specific failure this policy exists to prevent.

---

## Jurisdiction

The clinical recommendation travels; the access pathway does not.

- **England** — NHS National Genomic Test Directory sets what is commissioned for which
  indication. Testing is ordered through the clinical service, usually via a Genomic
  Laboratory Hub. Scotland, Wales and Northern Ireland have related but separate
  arrangements — do not assume the English directory applies.
- **United States** — ACMG 2021 is the clinical anchor; access runs through payer
  coverage policy, prior authorisation, and a defined appeals route on denial. Coverage
  differs by plan, and Medicaid differs by state.
- **Elsewhere** — name the clinical recommendation, and say plainly that you do not know
  the local access pathway rather than mapping US or UK assumptions onto it.

**Always ask where the person is** before writing anything about access. If they have not
said, the honest output covers the clinical recommendation and stops at the access
question.

---

## The gap logic

For testing already done, what it could not have found is answerable from the assay alone,
without knowing anything about the person. This is the most reliable content the skill
produces and the least often delivered.

The rules are in `assets/indication_index.json` under `test_gaps`. The ones that matter
most in practice:

- **A normal microarray is not a completed workup.** It cannot see sequence variants at
  all. This is the most common stopping point in an autism or ID pathway.
- **A panel is fixed at its version date.** Ask which panel and which version. A normal
  result on a 2018 panel says nothing about genes described since.
- **FMR1 repeat sizing is a separate assay.** Its absence is a gap in its own right.
- **Singleton exome is weaker than trio.** Without parental samples, interpretation of
  uncertain variants is materially limited.

**State the gap; do not inflate it.** "This test could not have detected sequence
variants" is true. "So there may well be something there" is not — it is a prediction, and
the same Tier 3 rule that governs the Navigator applies here.

---

## Reanalysis versus new testing

These are different requests with different costs and different answers, and they get
muddled.

- **Reanalysis** re-examines existing sequencing data against current knowledge. Cheaper,
  often possible without a new sample, and worth asking about when a non-diagnostic result
  is more than roughly two years old.
- **New testing** is a fresh assay, usually because the original test could not have found
  the answer — a microarray where an exome is indicated.

Establish which is being asked for before drafting anything. And check the report date:
recommending reanalysis of a recent report wastes a request and undermines the rest.

---

## Refusals

Where a request has already been declined:

1. **Find out what was actually declined and why** — the test, the indication, or the
   route. A refusal on eligibility grounds is a different problem from a refusal on
   funding grounds.
2. **Point at the defined review route.** Most systems have one. Naming it factually is
   the help.
3. **Do not coach an adversarial posture.** The clinical team is usually not the obstacle,
   and a family who arrives combative loses ground they needed.
4. **Do not speculate about motive.** You do not know why a decision was made.

---

## What never appears in output

- Eligibility criteria, age thresholds or yield figures stated from memory
- "You qualify", "this will be approved", "they have to fund this"
- A clinical feature the person did not actually report
- A prediction that testing will find something
- Legal advice, or a claim about what a payer is obliged to do
