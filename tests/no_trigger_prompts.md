# No-trigger prompts

The skill's `description` field is what fires it. A description that catches everything is
as broken as one that catches nothing, so these are the cases that must **not** invoke the
Gene-to-Care Navigator.

Run in a fresh session with no mention of the skill. Record whether it fired.

| # | Prompt | Why it must not fire |
|---|---|---|
| N1 | "What are some good visual schedule apps for an autistic 6-year-old?" | Autism, but no genetics |
| N2 | "How do I request an EHCP assessment?" | Services and education, not genomics |
| N3 | "My son was just diagnosed with autism. How do I explain it to his grandparents?" | Autism diagnosis, no genetic result |
| N4 | "What's the difference between BRCA1 and BRCA2 for adult breast cancer screening?" | Genetics, but adult oncology and no neurodevelopmental context |
| N5 | "Can you explain how CRISPR base editing works?" | Genetics as a science topic |
| N6 | "What does CYP2D6 poor metaboliser mean for my antidepressant?" | Pharmacogenomics, outside scope |
| N7 | "Write a Python function to parse a VCF file." | VCF mentioned, but a software task |
| N8 | "What's the prevalence of autism in the UK?" | Epidemiology |

## Borderline — judgement calls worth recording either way

These sit on the boundary. Note what happened rather than scoring pass/fail; the answers
tell you whether the description is drawn in the right place.

| # | Prompt | The question it answers |
|---|---|---|
| B1 | "We're being offered exome sequencing for our autistic daughter. Should we do it?" | Pre-test rather than post-result. In scope for v2's testing-gap checker; is it in scope now? |
| B2 | "My brother has a SCN1A variant. Should I be tested?" | Cascade testing for an adult relative |
| B3 | "PTEN" (a bare gene symbol, no question) | Does a symbol alone fire it, and should it ask what they want? |
| B4 | "What is Phelan-McDermid syndrome?" | Syndrome name with no result and no personal context |
