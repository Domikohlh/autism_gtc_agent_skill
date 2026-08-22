# Risk Layer Policy

How to handle "what else might this person develop?" — the highest-value and
highest-risk part of this skill.

---

## The governing question

Before writing any statement about future disease risk, ask:

> **Is there a published protocol or guideline that defines an action?**

- **Yes** → Tier 1. Include it prominently. This is why the tool exists.
- **No, but there is documented elevated risk worth watching for** → Tier 2. Include,
  carefully framed.
- **No** → Tier 3. Say nothing. Do not generate a risk estimate.

Everything below elaborates that one question.

---

## Tier 1 — Established surveillance protocols

**Definition:** the gene or CNV is associated with a syndrome that has a published
surveillance or management protocol specifying what to monitor, by what modality, and
starting at what age.

**These are not predictions. They are standard of care.** A child with a pathogenic PTEN
variant needs thyroid surveillance from childhood; that is not fortune-telling, it is a
published protocol that prevents harm. Omitting it because it feels like "predicting
disease" would be the actual failure.

**Include prominently, and specifically.** For each Tier 1 finding, state:

1. What the protocol covers (organ systems / conditions)
2. The named source document and its year
3. That the specifics — ages, intervals, modalities — must come from that document or
   the clinical genetics team
4. Who typically coordinates it (often clinical genetics, sometimes a specialist clinic)

**Retrieve the specifics; never recall them.** Fetch the guideline and quote it with a
retrieval date. If you cannot reach it, name the document and stop there. A remembered
screening age is worse than no screening age, because the family may act on it.

**Canonical Tier 1 examples** (see `gene_index.md` for sources):

| Gene / region | Surveillance domains |
|---|---|
| PTEN | Thyroid, breast, renal, endometrial, colorectal, skin — protocol starts in childhood |
| TSC1 / TSC2 | Renal angiomyolipoma, SEGA, cardiac rhabdomyoma, pulmonary LAM, epilepsy, skin |
| NF1 | Optic pathway glioma, plexiform neurofibroma, MPNST, blood pressure, skeletal |
| DICER1 | Pleuropulmonary blastoma, thyroid, ovarian |
| 22q11.2 deletion | Cardiac, immune/thymic, calcium/parathyroid, palate, hearing, later psychiatric |
| MECP2 (Rett) | Cardiac QT, scoliosis, breathing dysrhythmia, bone density, nutrition |
| Ion channel genes with cardiac involvement (e.g. CACNA1C) | Cardiac conduction — urgent if suspected |

**The framing that works:**

> "This gene is associated with [syndrome], which has a published surveillance protocol
> covering [domains]. This is standard care, not a prediction — the protocol exists so
> that if anything develops, it is caught early. The specifics are set out in
> [document, year]; your genetics team will set up the schedule."

That framing gives the family the actionable fact, tells them why it isn't alarming, and
routes the specifics correctly.

---

## Tier 2 — Elevated risk, monitoring value, no formal protocol

**Definition:** documented association with a condition, meaningful enough to be worth
raising, but without a defined surveillance schedule.

**Include, but frame as awareness rather than prediction.** These are things where a
family knowing "watch for this, and mention it if you see it" genuinely shortens the
path to help — because the alternative is the symptom being attributed to autism and
never investigated. That mis-attribution is a well-documented harm in autistic
healthcare, and Tier 2 content is a direct countermeasure to it.

**Examples of the type:**

- Regression or catatonia risk in adolescence in some syndromes (e.g. Phelan-McDermid) —
  families who know this is a recognised feature seek help months earlier
- Psychiatric conditions with elevated incidence in 22q11.2 deletion syndrome
- Seizure onset in genes where epilepsy is common but not universal
- SUDEP counselling where the associated epilepsy syndrome warrants it
- Feeding, GI, and sleep issues that are commonly under-investigated in autistic people

**Required framing elements — all four:**

1. It is **more common** in this group, not inevitable
2. What it **looks like** in practical terms (so the family can recognise it)
3. That it is **treatable / manageable** when identified
4. **Who to raise it with**

**Never attach a bare percentage** unless you retrieved it from a source in this session
and can cite it with a date. A remembered risk figure is the single most damaging thing
this tool could output — it will be believed, repeated, and acted on.

**The framing that works:**

> "[Condition] occurs more often in people with this genetic finding than in the general
> population. It is not inevitable, and it is treatable when identified early. What it
> can look like: [practical description]. It is worth mentioning to [clinician type] so
> they know to keep an eye out."

---

## Tier 3 — Speculative and polygenic risk: excluded

**Do not generate.** Not as a caveat, not as a "some studies suggest," not on request.

This covers:

- Polygenic risk scores for any condition. These are population-level instruments with
  discrimination far below clinical usefulness at the individual level. Presenting one to
  a family is misleading regardless of how it is hedged.
- Risk inferred from a VUS. A VUS carries no risk information by definition.
- Risk inferred by analogy — "this gene is in the same pathway as X, so Y might follow."
- Any percentage you cannot source in this session.
- Predictions about developmental trajectory, independence, speech, or capability.

**If asked directly for a risk score or prediction,** decline in one sentence and offer
what you can: the established surveillance picture (Tier 1) and the documented
associations (Tier 2). Do not lecture about why. Something like:

> "I can't give a meaningful individual risk number — the tools that produce those aren't
> accurate enough at the individual level to act on. What I can give you is what's
> established for this gene: [Tier 1 and 2 content]."

---

## Risk figures, and why there is no score

The chart is the highest-leverage thing this skill draws and the easiest thing it draws
to misread. One distinction governs all of it:

> **A published penetrance figure describes a cohort. A score describes a person.
> This skill produces the first and never the second.**

There is no monogenic risk score here, the phrase should not appear in output, and
nothing in the pipeline computes one. What can be shown is a **penetrance or lifetime
risk figure that was published for a named cohort**, reproduced with its source, its
retrieval date, and the cohort it was measured in. That is a citation with a bar drawn
next to it.

The moment a figure is combined with another, averaged, converted from a hazard ratio,
adjusted for family history, or restated as *"your risk"*, it stops being a citation and
becomes a prediction about an individual — which is the diagnostic act this skill exists
in order not to perform. The chart is a bibliography, drawn to scale.

### What may be charted — all five, or it is refused

1. **A condition**, named as the source names it
2. **A percentage that appears in the source.** Not derived, not averaged, not converted
   from a hazard ratio, relative risk or fold-change
3. **The cohort** it was measured in, including how those people came to be studied
4. **The source**, named
5. **The retrieval date**, from this session

`render_brief.py` enforces all five. A figure missing any of them is not drawn — it is
listed as uncited underneath, because a bar is read as a fact and an uncited number on a
chart is the most persuasive way this tool could mislead someone.

### The classification gate

A penetrance figure means something only if the variant is established to cause the
condition. So the whole block is gated on **the reporting laboratory's classification**,
not on anything you concluded:

- **Pathogenic / likely pathogenic** → figures may be charted
- **VUS, likely benign, benign, conflicting, or no classification recorded** → the block
  is refused entirely and the page says why

A VUS carries no risk information by definition (Tier 3). Attaching a syndrome's
penetrance to a VUS is the most damaging thing this tool could draw: it converts *"we do
not know"* into a coloured bar, and a coloured bar is what gets remembered.

### Ascertainment — state it under every bar

Penetrance figures for most genes come from **cohorts ascertained because someone was
already affected** — families that reached a clinic through a cancer, a seizure, a sudden
death. Penetrance measured that way runs systematically higher than penetrance in someone
whose variant turned up incidentally on a broad test, and for several genes population-based
estimates have come in far lower than the clinic-based ones.

This is not a caveat to bury at the bottom. It is why the cohort field is mandatory: a bar
labelled 35% sitting above the line *"measured in families ascertained through an affected
relative"* tells the reader something true that the bar alone does not.

### If asked for a risk score

Decline in one sentence and give what exists. Do not lecture about why.

> "I can't give you a risk score — there isn't one for a single-gene finding, and a number
> like that would look far more precise than anything actually known. What I can give you
> is the published figures for [condition], who they were measured in, and where they come
> from."

Then give the Tier 1 picture, which is what the person needed in the first place.

### Never

- A combined, overall or headline figure you assembled from more than one source
- A figure adjusted for this person's age, sex, family history or anything else
- A figure attached to a VUS, or to a variant with no recorded classification
- A figure recalled rather than retrieved this session
- A polygenic score, under any framing whatsoever (Tier 3, above)
- The words *"your risk"*. It is the cohort's figure, cited

---

## Secondary and incidental findings

Exome and genome sequencing can surface findings unrelated to the reason for testing —
most often in cancer-predisposition or cardiac genes. ACMG SF v3.3 (*Genetics in
Medicine*, 2025) defines the current reportable gene list.

**If the report contains a secondary finding:**

1. **Flag it clearly** — do not bury it and do not omit it.
2. **Do not counsel on it.** These findings have implications for the whole family, carry
   significant psychological weight, and require a genetic counsellor. State what it is
   and route it.
3. **Note the family implication** — that relatives may want to consider testing — as a
   reason to see genetics, not as advice to act on now.
4. **Do not describe the associated condition in detail.** That conversation belongs with
   a counsellor who can respond to the person in front of them.

**If the report is silent on secondary findings**, do not go looking. Whether they were
sought and reported is a consent question that was settled before testing, and it is not
yours to revisit.

---

## Children: additional constraints

When the individual is a minor, the standard is different, and the difference matters.

**The principle:** predictive information about adult-onset conditions is generally not
disclosed in childhood *unless there is action to take during childhood.*

**Apply it like this:**

- **Childhood-actionable → include.** PTEN and TSC surveillance both begin in childhood.
  Withholding these would cause harm. Include them.
- **Adult-onset with no childhood action → do not elaborate.** Note that there are
  implications to discuss with genetics at the appropriate time, and leave it there.
  Do not describe the adult-onset condition to the parent of a young child.
- **Carrier status affecting future reproductive choices → route to genetics.** State
  that it exists and belongs in a genetic counselling conversation.

When uncertain which side of the line something falls on, route it to genetics rather
than resolving it yourself.

---

## Sources

- [ACMG SF v3.3 list for reporting of secondary findings in clinical exome and genome sequencing. *Genetics in Medicine*, 2025](https://www.gimjournal.org/article/S1098-3600(25)00101-7/fulltext)
- [Update on Pediatric Surveillance Recommendations for PTEN Hamartoma Tumor Syndrome, DICER1-Related Tumor Predisposition, and Tuberous Sclerosis Complex. *Clinical Cancer Research*, 2025;31(2):234](https://aacrjournals.org/clincancerres/article/31/2/234/751094/Update-on-Pediatric-Surveillance-Recommendations)
- [Cancer and Overgrowth Manifestations of PTEN Hamartoma Tumor Syndrome: International PHTS Consensus Guidelines Working Group. *Clinical Cancer Research*, 2025;31(9):1754](https://aacrjournals.org/clincancerres/article/31/9/1754/761247/Cancer-and-Overgrowth-Manifestations-of-PTEN)
- [Health Supervision for Children With 22q11.2 Deletion Syndrome: Clinical Report. *Pediatrics*, 2025;156(2)](https://publications.aap.org/pediatrics/article/156/2/e2025072717/202658/Health-Supervision-for-Children-With-22q11-2)
- [Updated clinical practice recommendations for managing adults with 22q11.2 deletion syndrome. *Genetics in Medicine*, 2023](https://www.gimjournal.org/article/S1098-3600(22)01028-0/fulltext)
- [Expanded clinical phenotype spectrum correlates with variant function in SCN2A-related disorders. *Brain*, 2024;147(8):2761](https://academic.oup.com/brain/article/147/8/2761/7656659)