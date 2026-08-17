# Output Templates

Two registers, written for different questions. The family version is **not** a simplified
clinician version.

- Families ask: *what does this mean for us, and what do we do?*
- Clinicians ask: *what is the evidence, and what am I obliged to act on?*

Adapt the sections to the case. Drop what doesn't apply — an empty "Surveillance" heading
reading "none identified" is worse than no heading. Keep the closing limits block in both.

---

## Template A — For the family

```markdown
# Understanding this genetic result

## What was found
[One or two sentences, plain language. Name the gene and what kind of change it is.
If a syndrome name applies, give it — families need the name to find their community.]

## What this means
[What the finding does and does not explain. Be direct. If it explains the
developmental picture, say so. If it doesn't, say that too.]

## What this does NOT mean
[Address the predictable fears directly. Common ones: that this predicts what the child
will be capable of; that it means something was done wrong; that a VUS means bad news.
Only include the ones relevant to this result.]

## Health monitoring that goes with this finding
[TIER 1 ONLY. Frame as standard care, not prediction. Name the domains, name the source
document, and say the specifics come from the genetics team. Omit this section entirely
if there is no Tier 1 content — do not pad it.]

## Things worth knowing about
[TIER 2 ONLY. For each: more common but not inevitable · what it looks like in practice ·
that it's manageable when caught · who to mention it to. Omit if nothing qualifies.]

## Where to find others
[Gene-specific organisation. Registry (usually Simons Searchlight). Any active natural
history study. These matter more to most families than anything above.]

## Questions to bring to your next appointment
[5-8 specific, answerable questions. Not "what does this mean" — questions that get a
useful answer, like "should we be seeing genetics regularly, or is this a one-off?"
and "is there monitoring we should be set up for, and who arranges it?"]

## What this document is and isn't
This summarises published information about this gene. It is not medical advice and
it is not a diagnosis. Every decision here belongs with your clinical team — bring
this to them.
```

**Tone notes for Template A**

- Identity-first language ("autistic person") unless the user's own usage differs.
- Never speculate about capability, independence, or trajectory.
- Do not use the word "risk" more than necessary; "worth monitoring" carries the same
  information with less alarm.
- If there is genuinely good news — a manageable finding, an active research community,
  an available treatment — say so plainly. Families get very little of that.

### Register discipline — read this before writing the family half

Testing showed the family register drifting long, technical and tutorial: definitions the
reader did not ask for, citations mid-sentence, and a teaching voice. All three make it
harder to use, and the family half is the one most people will actually read.

**The fix for a technical term is deletion, not definition.** A tutor explains
"haploinsufficiency"; a useful brief never uses the word. Define a term only when the
family will have to say it themselves — the gene symbol and the syndrome name, because
those are what they need to find their community, book the right clinic, and search. Every
other term should be replaced by what it means in practice, not followed by a gloss.

- ✗ "This is a de novo loss-of-function variant, meaning it arose spontaneously rather
  than being inherited, and results in haploinsufficiency of the gene product."
- ✓ "This change was not inherited from either parent — it happened for the first time in
  your daughter."

**No citations in the family half.** No journal names, no author-year, no URLs mid-sentence.
The evidence belongs in the clinician section, which is where anyone checking it will look.
Where a family needs to know a protocol exists, name the body that publishes it in plain
words — "there is a published monitoring schedule, and your genetics team will have it" —
and nothing more.

**Be directive.** Say who does what next. "Ask your GP to refer you to clinical genetics"
is usable; "it may be worth considering whether a referral would be appropriate" is not.
Where the reader has a decision to make, say what the options are and who decides.

**Length.** Aim for one screen per section and under 800 words for the whole family half.
If a section needs more, it is usually carrying clinician content that belongs in the other
register. Cut rather than compress — a shorter brief that gets read beats a complete one
that does not.

**Order by what they do next**, not by what is scientifically interesting. Anything
time-critical goes first. What was found comes before what it means. What to do comes
before why.

---

## Template B — For the clinician

```markdown
# Genomic result summary — [gene / region]

## Finding
| Field | Value |
|---|---|
| Gene / region | |
| Transcript | |
| HGVS (c. / p.) | |
| Zygosity | |
| Inheritance | |
| Classification | |
| Test type | |
| Report date | |

## Gene–disease association
[Association and its validity. Cite ClinGen gene-disease validity where available.
Note if the association is limited or disputed.]

## Established surveillance — Tier 1
[Domains covered, source document with year, retrieval date. State that specifics are
per the cited document. Do not paraphrase ages or intervals from memory.]

## Documented associations without formal protocol — Tier 2
[Condition, nature of the association, practical presentation, source.]

## Management considerations
[Medication-relevant issues (e.g. sodium channel blocker considerations where direction
of effect is established or unestablished). Anaesthetic considerations. Anything
time-critical — cardiac involvement goes at the top, not buried.]

## Secondary findings
[Present / absent / not assessed. If present: name it, note the family-cascade
implication, route to genetic counselling. Do not counsel here.]

## Uncertainty and limitations
[Explicitly: what this result does not establish. Any VUS and why it is not actionable.
Where direction of effect is unknown and why that matters clinically.]

## Testing performed, and what it could not detect
[The assay's blind spots, from `indication_lookup.py --had`. Mechanical and near-certain:
a microarray cannot see sequence variants; a panel cannot see genes described after its
version date — state the version or say it must be obtained; an exome sees most repeat
expansions poorly; FMR1 repeat sizing is a separate assay. State the gap; do not inflate
it into a diagnosis-in-waiting.]

## Further testing indicated
[What is recommended for this clinical picture, and by which named authority, quoted with
a retrieval date. Distinguish explicitly:
  · clinical recommendation — published, and it travels;
  · eligibility — a policy question for the health system and clinical service.
Never assert eligibility. Where the report is non-diagnostic and older than roughly two
years, reanalysis of existing data and new testing are different requests — say which is
being described. See `references/testing_indications.md`.]

## Suggested next steps
[Parental/segregation testing. Reanalysis timing if the report is stale. Referrals.
RNA or functional testing if it would resolve a specific question — name the question.
Who holds each action.]

## Sources
[Every clinical assertion above, with retrieval date.]
```

**Tone notes for Template B**

- Do not soften. Clinicians want the finding and the evidence grade.
- Time-critical items — cardiac conduction, immune status affecting live vaccines,
  hypocalcaemia risk — go first, regardless of document structure.
- State evidence strength explicitly. "Consensus guideline" and "single case series" are
  different things and the distinction changes what a clinician does.
- Retrieval dates on everything. Guidelines move.
- **The testing-gap sections are for this register, not the family one.** A clinician,
  clinical scientist or bioinformatician picks up the follow-up here: what was not
  covered, what is indicated, whose authority says so, what to request. The family half
  gets at most one plain directive line — "the 2019 test could not look at individual
  genes; ask the genetics team whether sequencing is available now" — and never the
  citations. Splitting it this way is the point: the detail is useful to the person who
  can act on it and is noise to the person who cannot.

---

## Assembling both

`scripts/render_brief.py` takes structured findings and writes both registers to one
file with a page break between, so the clinician section can be handed over intact.

Deliver the family version first in conversation. That is who is usually asking.