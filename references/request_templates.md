# Request Templates

Two outputs, both for a human to review and send. Read
`references/testing_indications.md` first — it decides what may be claimed here.

- **Talking points** — for the person, to use in the appointment.
- **Request draft** — for the person *or* their clinician to edit and send themselves.

---

## The rule that governs both

**You draft; a human checks and sends.** Never present a draft as ready to go unread, and
never send anything. Say this inside the document, not only in conversation — drafts get
separated from the chat they came from.

**Only features the person actually stated go in a draft.** Not inferred, not typical for
the condition, not rounded up. A request that overstates the picture fails on review and
costs the sender credibility they will need later.

---

## Placeholders, not identifiers

A request needs clinical features and dates of testing. It does not need a name, date of
birth, or record number to be drafted — the sender fills those in on their own machine.

Use square-bracket placeholders throughout: `[NAME]`, `[DATE OF BIRTH]`, `[NHS/MRN]`,
`[CLINIC]`, `[REFERRER]`. If the user has already given you identifying details, still
write placeholders into the document; keep the details in conversation where they are not
saved to a file. See `references/data_privacy.md`.

---

## Template A — Talking points

```markdown
# Asking about genetic testing — what to raise

## What to ask for
[The specific test, in plain words. "Exome sequencing, ideally with both parents' samples"
— not "further genomic investigation".]

## Who to ask
[Named role, not an institution. The paediatrician, the GP for a referral, the clinical
genetics service. Say which one holds the decision.]

## Why it is being asked for
[One or two sentences: the clinical features, and the recommendation that covers them.
Plain words, no citation in this half.]

## What has already been done, and what it could not find
[Test, roughly when, and the gap. "The microarray in 2019 was normal. That test looks for
missing or extra pieces of chromosome — it cannot see single-letter changes in a gene,
which is what exome sequencing looks for."]

## What to bring
[Copies of previous reports, including the normal ones. Dates. Any family history.]

## If the answer is no
[The defined review route, factually. Who to ask about it. That a refusal is often about
criteria or funding rather than clinical judgement, and that asking which one it was is a
fair question.]

## What this is and isn't
These are points to raise, not medical advice. Whether testing is right and whether it is
available are decisions for your clinical team.
```

**Tone for Template A.** Plain and directive — the same register discipline as the
Navigator's family half. No citations, no journal names, no URLs. Say who does what.
Under 500 words.

---

## Template B — Request draft

One shape, two wordings. The clinical content is identical; what differs is the authority
named and the route.

```markdown
# [Referral request / Funding request] — genetic testing

**To:** [RECIPIENT — service or payer]
**Re:** [NAME], date of birth [DATE OF BIRTH], [NHS NUMBER / MRN]
**From:** [REFERRER OR SENDER]
**Date:** [DATE]

## Request
[The specific test requested, and for whom — proband alone or with parents.]

## Clinical features
[Only what the person reported. Bulleted, factual, dated where known. No adjectives.]

## Testing already performed
| Test | Date | Result |
|---|---|---|
| [e.g. chromosomal microarray] | [date] | [normal / non-diagnostic / VUS] |

[One line on what that testing could not have detected.]

## Basis for the request
[The authority, quoted and cited with a retrieval date. For a funding request, the
governing policy document and the criterion being relied on. This is the only section
where citations belong.]

## What is being asked
[The decision sought, in one sentence: a referral, an approval, or a reconsideration.]

---
*Drafted for review. The sender should check every clinical statement against the
records before sending. Nothing here has been verified against a medical record, and
nothing has been sent.*
```

### UK / NHS wording

- Address the **clinical genetics service** or the referring clinician; testing is
  ordered through the service, not requested from a payer directly.
- Cite the **NHS National Genomic Test Directory** entry for the indication, by version
  and retrieval date.
- Frame it as *"whether [NAME] meets the criteria for [test] under indication [code, if
  retrieved]"* — a question about criteria, not a demand.
- Nations differ. Do not cite the English directory for Scotland, Wales or NI.

### US / payer wording

- Address the **clinician** for a referral, or the **payer** for prior authorisation or an
  appeal — and say which, because they need different documents.
- Cite **ACMG 2021** for the clinical recommendation, and the **plan's own medical policy**
  for coverage. Both, not one.
- For a denial, name the specific denial reason being addressed and the plan's stated
  appeal route.
- Medical-necessity language is the payer's framing; use their terms where retrieved, but
  never assert that a plan is obliged to cover anything.

---

## Before handing either over, check

- [ ] Every clinical feature came from the user, not from you
- [ ] No eligibility determination — no "qualifies", "will be approved", "must fund"
- [ ] Every criterion or figure carries a source and a retrieval date, or is absent
- [ ] Identifiers are placeholders
- [ ] The review-and-send statement is in the document itself
- [ ] Talking points carry no citations; the request draft carries them only in **Basis**
- [ ] Jurisdiction is right, and stated
