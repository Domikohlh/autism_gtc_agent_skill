# Data Privacy

What to do about the fact that a genetic test report is among the most sensitive
documents a person will ever hold. It concerns a named individual, it is frequently
about a child, and it carries information about relatives who never consented to
anything.

**The redaction in the scripts is a safety net, not permission.**

---

## What the code already does

| Where | What it does |
|---|---|
| `scripts/phi.py` | The single identifier ruleset — name, DOB, record/hospital number, NHS number, SSN-shaped strings, lab accession, email. Shared, so the parser and the renderer cannot drift apart |
| `scripts/parse_report.py` | Redacts every rule above from the whole document *before* parsing. `--no-redact` opts out and is for synthetic reports only |
| `scripts/parse_report.py` | Drops dates labelled as birth or collection dates — wrong answers *and* identifiers |
| `scripts/render_brief.py` | Scans the assembled document with the same ruleset and **refuses to write the file** if it finds an identifier |

Writing the file is the step that makes a leak durable, so that is the step that stops.
`--allow-phi` overrides it and should be a deliberate decision, not a way past a warning.

---

## What it cannot do, and what that means for you

**Regex redaction is pattern-matching, not comprehension.** It catches labelled
identifiers. It misses a name in running prose ("Jack's results show…"), an unlabelled
address, a referring clinician, an unusual date format, and anything mangled by OCR.
**The obligation is yours, not the regex's** — read what you are about to write.

**De-identified is not anonymous.** A variant is itself identifying. Genomic data is
re-identifiable in principle, and stripping every name and number does not change that.
Under GDPR it remains special category data (Art. 9); under HIPAA, genetic information is
PHI and is covered by GINA. Treat parser output as identifiable health data however clean
it looks.

**Running this skill is a disclosure.** The report's content enters the context of
whatever model is running, under that provider's terms rather than this repository's. If
the user has not obviously considered that, say so once, plainly, before working through a
real report — then respect their answer. It is their decision, not yours.

---

## In conversation and in files

- **Never write identifiers into an output file**, even when asked directly. Offer to
  explain how the person can add a name themselves after the file is produced. Do not
  lecture about privacy law.
- **Follow the user's lead in conversation only.** If they use their child's name, using
  it back is natural. It still does not go into a document.
- **A child's genetic data belongs to the child**, including the parts that will matter to
  them as an adult. A parent can consent today; that does not settle what should be
  written down, retained, or shared later.
- **Do not compile.** Family structure, a rare syndrome plus a location, or a distinctive
  variant can identify a person on its own.
- **Intermediates persist.** `findings*.json` and `brief*.md` sit on disk and contain
  everything. Mention deleting them when the work is done.

If the report is the user's own, or their child's, it is theirs to share. Leave the
redaction defaults on so identifiers do not reach a file they later hand to someone else.

**Nothing here is legal advice.** Where real patient data is involved and the user is not
certain what applies, point them at their DPO, IG lead, privacy officer, or IRB.
