#!/usr/bin/env python3
"""
Parser-layer regression test over the synthetic fixture corpus.

This checks the *scripts*, not the skill. It asserts what the parser structurally
extracted — gene, classification, counts, the date it chose — and says nothing
about whether the resulting brief was clinically good. That judgement lives in
`cases.md` and needs a human.

Expectations below were recorded from verified runs, not written from intent. If
one fails, either the parser regressed or the parser improved; read the diff and
decide which, then update this file deliberately.

Usage:
    python tests/smoke_test.py
    python tests/smoke_test.py -v        # print every extracted record
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
PARSER = ROOT / "scripts" / "parse_report.py"
INDICATIONS = ROOT / "scripts" / "indication_lookup.py"

# indication_lookup.py: free-text clinical picture -> which indications match.
# The two failure modes both overpromise, so both are pinned here:
#   - a single feature matching a two-feature indication ("autism" alone)
#   - a negated feature counting as present ("no developmental delay")
INDICATION_EXPECTED: list[tuple[str, list[str], bool]] = [
    # features, expected indication keys (order-insensitive), matched_via_absence
    ("autism, learning delay, macrocephaly", ["asd_with_dd_or_id"], False),
    ("autism, global developmental delay, heart murmur",
     ["asd_with_dd_or_id", "dysmorphism_or_congenital_anomaly"], False),
    # "autism" alone must NOT reach the with-delay indication.
    ("autism", ["asd_without_dd_or_id"], True),
    # A negated feature must not count as present.
    ("autistic, academically ahead, no developmental delay",
     ["asd_without_dd_or_id"], True),
    # ...and a negation elsewhere must not suppress a real feature.
    ("autistic, no seizures, global developmental delay", ["asd_with_dd_or_id"], False),
    ("autism, epilepsy, regression",
     ["asd_with_dd_or_id", "epilepsy_with_ndd"], False),
    # Epilepsy without a neurodevelopmental feature is out of scope, not a match.
    ("epilepsy only", [], False),
    ("sibling tested for the same thing", ["family_history"], False),
    ("previous exome came back normal", ["prior_nondiagnostic_reanalysis"], False),
    # A negator only governs its own clause. A fixed character window got this
    # wrong both ways: missing a long negation, then suppressing across a comma.
    ("autism without any significant developmental delay",
     ["asd_without_dd_or_id"], True),
    ("autistic, denies any history of seizures, global developmental delay",
     ["asd_with_dd_or_id"], False),
    # A passing mention of a sibling is not a family-history indication.
    ("his brother's paperwork got mixed up", [], False),
    # ...and "my son was diagnosed" is a parent describing the proband, not a
    # family history. Kinship words identify either; the phrase is what marks it.
    ("my son was diagnosed autistic, global developmental delay",
     ["asd_with_dd_or_id"], False),
    ("family history of intellectual disability", ["family_history"], False),
    # S7: dysmorphism alongside ASD+ID must reach BOTH indications, since each
    # carries a different authority set.
    ("autism, moderate intellectual disability, dysmorphic features, hypertelorism",
     ["asd_with_dd_or_id", "dysmorphism_or_congenital_anomaly"], False),
]

# fixture -> expected structure.
#   genes/cnvs/repeats : ordered lists of the identifying field
#   date               : the report date the parser must choose
#   classes            : classification per variant, in order
#   must_flag          : substrings that must appear somewhere in warnings
#   must_not_contain   : substrings that must NOT appear anywhere in the JSON
EXPECTED: dict[str, dict] = {
    # --- reports: one per condition category the skill claims to cover, plus
    # the two case types nothing else exercises (repeat expansion, negative).
    "reports/01_exome_pten_neurodevelopmental.txt": {
        "date": "12 March 2026", "test_type": "exome",
        "genes": ["PTEN", "CHD8"], "classes": ["Pathogenic", "VUS"],
        "must_flag": ["Secondary/incidental findings referenced"],
        "must_not_contain": ["7781204", "04/09/2017", "MCG-2026-004411"],
    },
    "reports/02_microarray_22q11_deletion.txt": {
        "date": "02 May 2026", "test_type": "microarray",
        "cnvs": [("22q11.21", "deletion", 1)],
        "must_not_contain": ["3391077", "22/05/2021"],
    },
    "reports/03_karyotype_trisomy21_down.txt": {
        # A karyotype carries no HGVS. The finding IS the ISCN string, captured
        # verbatim and never interpreted: 47,XY,+21 and 46,XY,t(14;21) differ by
        # a few characters and mean very different things.
        "date": "01 July 2026", "test_type": "karyotype",
        "genes": [], "cnvs": [], "repeats": [],
        "karyotypes": ["47,XY,+21"],
        "must_not_contain": ["7730155", "19/06/2026"],
    },
    "reports/04_panel_mybpc3_cardiac.txt": {
        "date": "27 March 2026",
        "genes": ["MYBPC3"], "classes": ["VUS"],
        "must_not_contain": ["4419277", "30/11/2008"],
    },
    "reports/05_newborn_pah_metabolic.txt": {
        # Second variant has no Gene: label of its own — the parser flags it
        # rather than attributing it, which is the conservative behaviour.
        "date": "29 July 2026",
        "genes": ["PAH", None], "classes": ["Pathogenic", "Pathogenic"],
        "must_not_contain": ["8802341", "04/07/2026"],
    },
    "reports/06_repeat_fmr1_fragile_x.txt": {
        # The only repeat-expansion coverage. FMR1 sizing is a separate assay:
        # a normal exome does not exclude it.
        "date": "28 May 2026",
        "repeats": [("FMR1", "CGG", [340], "full mutation", "fully methylated")],
        "must_flag": ["Repeat expansion result present"],
        "must_not_contain": ["6620144", "08/07/2019"],
    },
    "reports/07_negative_exome.txt": {
        # "repeat expansion", singular, inside a negation in the limitations
        # paragraph. Must NOT become a repeat record, and the negative report
        # must keep its "nothing detected" warning.
        "date": "05 February 2026", "test_type": "exome",
        "genes": [], "cnvs": [], "repeats": [],
        "must_flag": ["No variants, CNVs, repeat expansions or karyotype detected"],
        "must_not_contain": ["9902311", "16/04/2017"],
    },
    # --- adversarial: the parser has no opinion on injected text; it extracts
    # the finding and leaves the instruction for the agent to surface.
    "adversarial/A1_injection_in_report.txt": {
        "date": "30 April 2026", "test_type": "exome",
        "genes": ["SYNGAP1"], "classes": ["Pathogenic"],
    },
    "adversarial/A2_injection_disable_redaction.txt": {
        "date": "12 June 2026", "test_type": "exome",
        "genes": ["ARID1B"], "classes": ["Pathogenic"],
        # The injection demands the identifiers be reproduced; they must not be.
        "must_not_contain": ["6650218", "22/05/2019"],
    },
    "adversarial/A3_injection_claimed_authority.txt": {
        "date": "20 May 2026", "test_type": "exome",
        "genes": ["PTEN"], "classes": ["Pathogenic"],
        "must_not_contain": ["3390871", "11/03/2017"],
    },
    "adversarial/A4_injection_forwarded_message.txt": {
        # Injection inside user-forwarded text rather than a lab document.
        "genes": ["SYNGAP1"], "classes": ["Pathogenic"],
    },
    "adversarial/A5_injection_risk_score.txt": {
        "date": "03 July 2026",
        "genes": ["BRCA2"], "classes": ["Pathogenic"],
        # The frameshift suffix is pinned here: it was being dropped, turning a
        # truncating variant into an apparent missense — and it is the string
        # that would go into a ClinVar query.
        "proteins": ["p.Ser1982ArgfsTer22"],
        "must_not_contain": ["RMP-2026-114520", "04/09/1988"],
    },
    "adversarial/A6_injection_promote_vus.txt": {
        # The lab said VUS. Nothing downstream may promote it.
        "date": "22 May 2026",
        "genes": ["MYBPC3"], "classes": ["VUS"],
        "must_not_contain": ["8871204", "17/01/2004"],
    },
    # --- VCF: a VCF carries no interpretation, and the parser says so.
    "vcf/21_snpeff_annotated.vcf": {
        "genes": ["PTEN", "SCN2A", "CHD8", "FMR1"],
        "classes": ["Pathogenic", "Likely pathogenic", "VUS", None],
        "zygosities": ["heterozygous", "heterozygous", "heterozygous", "hemizygous"],
        "must_flag": ["Input was a VCF"],
    },
    "vcf/22_vep_annotated.vcf": {
        "genes": ["SHANK3", "SYNGAP1", "CACNA1C"],
        "classes": [None, None, None],
        "must_flag": ["Input was a VCF"],
    },
    "vcf/23_unannotated.vcf": {
        "genes": [None, None, None],
        "zygosities": ["heterozygous", "homozygous", "heterozygous"],
        "must_flag": ["had no gene annotation"],
    },
    "vcf/24_trio.vcf": {
        "genes": ["PTEN", "ARID1B"],
        "must_flag": ["Input was a VCF", "3 samples"],
    },
    "vcf/27_homref_nocall.vcf": {
        # 0/0 and 0|0 rows are not findings; ./. is kept but flagged.
        "genes": ["SCN2A", "CHD8"],
        "zygosities": [None, "heterozygous"],
        "must_flag": ["2 record(s) were homozygous reference"],
    },
    "vcf/28_sample_order.vcf": {
        # Proband is the THIRD sample. Default reads the first and says so.
        "genes": ["SHANK3"],
        "zygosities": ["heterozygous"],
        "must_flag": ["Genotypes were read from 'mother'", "3 samples"],
    },
    # --- .txt fallback for platforms that refuse .vcf uploads -------------
    # A clean rename loses nothing. What a *conversion* does to the content is
    # what costs, and each of these pins one measured mode.
    "vcf_as_txt/A_clean_rename.vcf.txt": {
        # Byte-identical to vcf/21, renamed. Must parse identically.
        "genes": ["PTEN", "SCN2A", "CHD8", "FMR1"],
        "classes": ["Pathogenic", "Likely pathogenic", "VUS", None],
        "zygosities": ["heterozygous", "heterozygous", "heterozygous", "hemizygous"],
        "must_flag": ["Input was a VCF"],
    },
    "vcf_as_txt/B_headers_stripped_snpeff.txt": {
        # SnpEff ANN field order is fixed by spec, so it survives header loss.
        "genes": ["PTEN", "SCN2A", "CHD8", "FMR1"],
        "zygosities": ["heterozygous", "heterozygous", "heterozygous", "hemizygous"],
        "must_flag": ["Input was a VCF"],
    },
    "vcf_as_txt/C_headers_stripped_vep.txt": {
        # VEP CSQ field order lives in the stripped header — gene and HGVS go
        # with it. The values are still present; nothing states what they are.
        "genes": [None, None, None],
        "zygosities": ["heterozygous", "heterozygous", "heterozygous"],
        "must_flag": ["format header", "had no gene annotation"],
    },
    "vcf_as_txt/D_data_rows_only.txt": {
        # No #CHROM line: falls out of the VCF path altogether. Genes survive
        # only because the prose parser finds HGVS inside the ANN= text.
        "genes": ["PTEN", "SCN2A", "CHD8", "FMR1"],
        "zygosities": [None, None, None, None],
    },
    "vcf_as_txt/E_tabs_to_spaces.txt": {
        # A rich-text paste. Rows are recovered, and the recovery is declared.
        "genes": ["PTEN", "SCN2A", "CHD8", "FMR1"],
        "zygosities": ["heterozygous", "heterozygous", "heterozygous", "hemizygous"],
        "must_flag": ["tab-free"],
    },
}

# Fixtures parsed with a non-default sample selection.
SAMPLE_EXPECTED: dict[str, dict] = {
    "vcf/28_sample_order.vcf": {
        "sample": "proband",
        "genes": ["PTEN", "SHANK3"],
        "zygosities": ["heterozygous", "homozygous"],
    },
}

# Every fixture must carry a marker identifying it as synthetic. This is the
# check that actually catches a real report dropped into the corpus — .gitignore
# can only stop git from committing one, and only by extension.
SYNTHETIC_MARKERS = ("Synthetic test document", "SyntheticTestFixture_NotRealPatientData")


# Every identifier planted anywhere in the corpus, checked against EVERY
# fixture's output rather than only its own. A per-fixture check passes by luck
# whenever the context window simply did not reach the header.
CORPUS_IDENTIFIERS = [
    "7781204", "04/09/2017", "MCG-2026-004411",
    "5540982", "17/11/2019", "NGD-88213-A",
    "3391077", "22/05/2021",
    "4470221", "30/01/2015",
    "6620144", "08/07/2019",
    "1120876", "12/03/2014",
    "8830145", "19/08/2022",
    "2245609", "25/12/2018",
    "9910334", "02/02/2020",
    "5567023", "14/06/2016",
    "4408871", "09/10/2024",
    "3320998", "27/04/2020",
    "7734012", "06/06/2018",
    "6041229", "31/03/2022",
    "5590117", "11/09/2021",
    "15/02/2019", "2026-DE-04471",
    "7712008", "21/09/2021",
    "2280551", "05/11/2023",
    "4419902", "13/01/2020",
    "5512094", "08/02/1979", "7730155", "19/06/2026",
    "4419277", "30/11/2008", "8802341", "04/07/2026",
    "6650218", "22/05/2019", "3390871", "11/03/2017",
    "9902311", "16/04/2017",
    "Testcase",
]

# Known and documented exception: fixture 17 carries its identifier in running
# prose with no label, which regex redaction cannot see. It exists to prove that
# limit, so it is exempt — see the privacy section of README.md.
LEAK_SCAN_EXEMPT = {"17_name_in_prose.txt"}


def parse(path: Path, sample: str | None = None) -> dict:
    cmd = [sys.executable, str(PARSER), str(path)]
    if sample:
        cmd += ["--sample", sample]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def check(name: str, spec: dict, verbose: bool) -> list[str]:
    record = parse(FIXTURES / name, sample=spec.get("sample"))
    blob = json.dumps(record)
    failures: list[str] = []

    def cmp(label, got, want):
        if got != want:
            failures.append(f"{label}: expected {want!r}, got {got!r}")

    if "date" in spec:
        cmp("report_date", record["report_date"], spec["date"])
    if "test_type" in spec:
        cmp("test_type", record["test_type"], spec["test_type"])
    if "genes" in spec:
        cmp("genes", [v["gene"] for v in record["variants"]], spec["genes"])
    if "classes" in spec:
        cmp("classifications", [v["classification"] for v in record["variants"]], spec["classes"])
    if "zygosities" in spec:
        cmp("zygosities", [v["zygosity"] for v in record["variants"]], spec["zygosities"])
    if "proteins" in spec:
        cmp("hgvs_p", [v["hgvs_p"] for v in record["variants"]], spec["proteins"])
    if "cnvs" in spec:
        cmp("cnvs", [(c["band"], c["kind"], c["copies"]) for c in record["cnvs"]], spec["cnvs"])
    if "karyotypes" in spec:
        cmp("karyotypes", [k["iscn"] for k in record["karyotypes"]], spec["karyotypes"])
    if "repeats" in spec:
        got = [
            (r["gene"], r["motif"], r["allele_sizes"], r["category"], r["methylation"])
            for r in record["repeats"]
        ]
        cmp("repeats", got, [tuple(x) for x in spec["repeats"]])

    for needle in spec.get("must_flag", []):
        if not any(needle in w for w in record["warnings"]):
            failures.append(f"missing warning containing {needle!r}")
    for needle in spec.get("must_not_contain", []):
        if needle in blob:
            failures.append(f"IDENTIFIER LEAK: {needle!r} present in output")

    if verbose:
        print(json.dumps(record, indent=2))
    return failures


def leak_scan() -> list[str]:
    """Cross-check every fixture's output against every planted identifier."""
    failures = []
    for name in EXPECTED:
        if Path(name).name in LEAK_SCAN_EXEMPT:
            continue
        blob = json.dumps(parse(FIXTURES / name))
        for identifier in CORPUS_IDENTIFIERS:
            if identifier in blob:
                failures.append(f"{name}: leaked {identifier!r}")
    return failures


def check_indications() -> list[str]:
    """Indication matching, which decides whether a picture looks eligible."""
    failures = []
    for features, expected, expect_absence in INDICATION_EXPECTED:
        out = subprocess.run(
            [sys.executable, str(INDICATIONS), "--features", features, "--json"],
            capture_output=True, text=True, check=True,
        )
        got = json.loads(out.stdout)
        keys = sorted(got["indications"])
        if keys != sorted(expected):
            failures.append(f"{features!r}: expected {sorted(expected)}, got {keys}")
        absence = bool(got.get("matched_via_absence"))
        if absence != expect_absence:
            failures.append(
                f"{features!r}: matched_via_absence expected {expect_absence}, got {absence}"
            )
    return failures


# render_brief.py: the gates in front of the risk chart. These exist because a bar
# is read as a fact — the figure is a citation of a cohort, never a score for the
# person in front of you, and every one of these cases is a way that distinction
# could quietly collapse.
#
# (label, findings, must appear in the clinician register, must NOT appear)
RISK_FIGURE_CASES: list[tuple[str, dict, list[str], list[str]]] = [
    (
        "pathogenic + all five fields draws the bar",
        {"clinician": {"finding_table": {"Classification": "Pathogenic"}},
         "risk_figures": [{"condition": "Thyroid cancer, lifetime", "percent": 35,
                           "cohort": "ascertained PHTS patients, n=3399",
                           "source": "PHTS Consensus 2025", "retrieved": "2026-08-18"}]},
        ["35%", "ascertained PHTS patients", "not a score"],
        ["No figures are shown"],
    ),
    (
        "likely pathogenic also draws",
        {"clinician": {"finding_table": {"Classification": "Likely pathogenic"}},
         "risk_figures": [{"condition": "Renal cell carcinoma", "percent": 12,
                           "cohort": "clinic-based cohort", "source": "S 2025",
                           "retrieved": "2026-08-18"}]},
        ["12%"],
        ["No figures are shown"],
    ),
    (
        "a VUS refuses the whole block",
        {"clinician": {"finding_table": {"Classification": "Variant of uncertain significance"}},
         "risk_figures": [{"condition": "HCM, lifetime", "percent": 60,
                           "cohort": "HCM probands", "source": "S 2024",
                           "retrieved": "2026-08-19"}]},
        ["No figures are shown"],
        ["60%"],
    ),
    (
        "likely benign is not rescued by the word 'likely'",
        {"clinician": {"finding_table": {"Classification": "Likely benign"}},
         "risk_figures": [{"condition": "Anything", "percent": 40,
                           "cohort": "a cohort", "source": "S 2025",
                           "retrieved": "2026-08-19"}]},
        ["No figures are shown"],
        ["40%"],
    ),
    (
        "conflicting classifications refuse the block",
        {"clinician": {"finding_table": {"Classification": "Conflicting classifications of pathogenicity"}},
         "risk_figures": [{"condition": "Anything", "percent": 40,
                           "cohort": "a cohort", "source": "S 2025",
                           "retrieved": "2026-08-19"}]},
        ["No figures are shown"],
        ["40%"],
    ),
    (
        "no classification recorded refuses the block",
        {"clinician": {"finding_table": {"Gene": "PTEN"}},
         "risk_figures": [{"condition": "Thyroid cancer", "percent": 35,
                           "cohort": "a cohort", "source": "S 2025",
                           "retrieved": "2026-08-18"}]},
        ["No figures are shown", "classification recorded in the finding table"],
        ["35%"],
    ),
    (
        "a figure with no cohort is not drawn",
        {"clinician": {"finding_table": {"Classification": "Pathogenic"}},
         "risk_figures": [{"condition": "Renal cell carcinoma", "percent": 34,
                           "source": "S 2025", "retrieved": "2026-08-18"}]},
        ["no cohort recorded"],
        ["34%"],
    ),
    (
        "a percent outside 0-100 is refused, not clamped to a full bar",
        {"clinician": {"finding_table": {"Classification": "Pathogenic"}},
         "risk_figures": [{"condition": "Overall", "percent": 350,
                           "cohort": "combined", "source": "derived",
                           "retrieved": "2026-08-18"}]},
        ["outside 0-100"],
        ["100%", "350%"],
    ),
    (
        "a retrieval date that is not a date is refused",
        {"clinician": {"finding_table": {"Classification": "Pathogenic"}},
         "risk_figures": [{"condition": "Thyroid cancer", "percent": 35,
                           "cohort": "a cohort", "source": "S 2025",
                           "retrieved": "last year"}]},
        ["no retrieval date"],
        ["35%"],
    ),
]


# The interactive panel and the audience boundary. The panel is modelled on a
# variant-browser UI whose original had a computed risk score and a penetrance
# dial; these cases pin the fact that neither came with it, that the figures
# never reach a family-facing surface, and that the tier slot cannot become an
# actionability verdict.
PANEL_CASES: list[tuple[str, dict, str, list[str], list[str]]] = [
    (
        "figures render on the clinician page",
        {"clinician": {"finding_table": {"Gene": "PTEN", "Classification": "Pathogenic"}},
         "risk_figures": [{"condition": "Thyroid cancer", "percent": 35,
                           "cohort": "ascertained cohort", "source": "S 2025",
                           "retrieved": "2026-08-18"}]},
        "clinician", ["35%", "Reference only", "not a diagnosis"], [],
    ),
    (
        "the family page carries no figure block at all",
        {"family": {"what_was_found": "A change was found."},
         "clinician": {"finding_table": {"Gene": "PTEN", "Classification": "Pathogenic"}},
         "risk_figures": [{"condition": "Thyroid cancer", "percent": 35,
                           "cohort": "ascertained cohort", "source": "S 2025",
                           "retrieved": "2026-08-18"}]},
        # Not merely "no figures": none of the machinery either. The panel
        # stylesheet is emitted with the panel, so a family page carries no
        # class names, no rules, and no comments belonging to it.
        "family", [],
        ["35%", "Published figures", "Reference only", "Thyroid cancer",
         "vptabs", "refonly", "cohort", "penetrance"],
    ),
    (
        "two cohort bases raise the toggle and keep both figures",
        {"risk_panel": {"findings": [{
            "label": "BRCA1", "locus": "17q21.31", "classification": "Pathogenic",
            "figures": [
                {"condition": "Breast carcinoma", "percent": 72, "basis": "clinic",
                 "cohort": "ascertained families", "source": "A 2025",
                 "retrieved": "2026-08-20"},
                {"condition": "Breast carcinoma", "percent": 46, "basis": "population",
                 "cohort": "unselected carriers", "source": "B 2026",
                 "retrieved": "2026-08-20"}]}]}},
        "clinician", ["72%", "46%", "Clinic-ascertained", "Population-based"], [],
    ),
    (
        "a VUS finding keeps its tab but shows no figure",
        {"risk_panel": {"findings": [{
            "label": "LRRK2 G2019S", "classification": "Variant of uncertain significance",
            "figures": [{"condition": "Parkinson disease", "percent": 28,
                         "cohort": "a cohort", "source": "S 2025",
                         "retrieved": "2026-08-20"}]}]}},
        "clinician", ["LRRK2 G2019S", "No figures are shown"], ["28%"],
    ),
    (
        "one finding refused does not suppress another that is allowed",
        {"risk_panel": {"findings": [
            {"label": "BRCA1", "classification": "Pathogenic",
             "figures": [{"condition": "Breast carcinoma", "percent": 72,
                          "cohort": "ascertained families", "source": "A 2025",
                          "retrieved": "2026-08-20"}]},
            {"label": "LRRK2", "classification": "VUS",
             "figures": [{"condition": "Parkinson disease", "percent": 28,
                          "cohort": "a cohort", "source": "S 2025",
                          "retrieved": "2026-08-20"}]}]}},
        "clinician", ["72%", "No figures are shown"], ["28%"],
    ),
    (
        "an actionability verdict is refused from the tier slot",
        {"risk_panel": {"findings": [{
            "label": "BRCA1", "classification": "Pathogenic",
            "surveillance_tier": "Tier III (Low Risk)",
            "figures": [{"condition": "Breast carcinoma", "percent": 72,
                         "cohort": "ascertained families", "source": "A 2025",
                         "retrieved": "2026-08-20"}]}]}},
        "clinician", ["72%"], ["Low Risk", "Tier III"],
    ),
]


def check_panel() -> list[str]:
    """Audience boundary, per-finding gates, and the closed tier vocabulary."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import render_brief
    except ImportError as exc:  # pragma: no cover - environment, not a regression
        return [f"could not import render_brief: {exc}"]

    failures = []
    for label, findings, audience, must, must_not in PANEL_CASES:
        page = render_brief.render_html(findings, audience)
        for needle in must:
            if needle not in page:
                failures.append(f"{label}: expected {needle!r} in the {audience} page")
        for needle in must_not:
            if needle in page:
                failures.append(f"{label}: {needle!r} must NOT appear in the {audience} page")

    # The page must stay script-free: it is emailed, opened offline and printed.
    page = render_brief.render_html(PANEL_CASES[2][1], "clinician")
    if "<script" in page.lower():
        failures.append("the interactive panel introduced a <script> tag")
    return failures


# SKILL.md frontmatter must satisfy the platform's upload rules. These are hard
# limits, not style: a description one character over 1024 is rejected at upload
# with nothing in the repository looking wrong, which is exactly the kind of
# failure that costs an afternoon. The body-length rule is Anthropic's stated
# guidance rather than a hard cap, so it is reported as a warning, not a failure.
FRONTMATTER_LIMITS = {"name": 64, "description": 1024}
SKILL_BODY_GUIDANCE = 500


def check_skill_frontmatter() -> tuple[list[str], list[str]]:
    """Returns (failures, warnings) for SKILL.md's YAML frontmatter."""
    path = ROOT / "SKILL.md"
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return ["SKILL.md has no YAML frontmatter block"], []

    front, body = m.group(1), m.group(2)
    failures, warnings = [], []

    fields = {}
    for key in FRONTMATTER_LIMITS:
        km = re.search(rf"^{key}:\s*(.*?)(?=\n[a-zA-Z-]+:|\Z)", front, re.S | re.M)
        if not km or not km.group(1).strip():
            failures.append(f"frontmatter is missing a non-empty '{key}'")
        else:
            fields[key] = km.group(1).strip()

    for key, limit in FRONTMATTER_LIMITS.items():
        value = fields.get(key)
        if value and len(value) > limit:
            failures.append(
                f"{key} is {len(value)} characters, over the {limit} limit by "
                f"{len(value) - limit} — the skill will be rejected at upload"
            )
        if value and ("<" in value or ">" in value):
            failures.append(f"{key} contains an angle bracket; XML tags are rejected")

    name = fields.get("name", "")
    if name and not re.fullmatch(r"[a-z0-9-]+", name):
        failures.append(f"name {name!r} must be lowercase letters, numbers and hyphens only")
    if re.search(r"anthropic|claude", name, re.I):
        failures.append(f"name {name!r} contains a reserved word")

    lines = len(body.splitlines())
    if lines > SKILL_BODY_GUIDANCE:
        warnings.append(
            f"SKILL.md body is {lines} lines; Anthropic's guidance is under "
            f"{SKILL_BODY_GUIDANCE}. Not an upload blocker — move detail into references/"
        )
    return failures, warnings


def check_risk_figures() -> list[str]:
    """Assert the chart gates. Failures here are the dangerous kind."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import render_brief
    except ImportError as exc:  # pragma: no cover - environment problem, not a regression
        return [f"could not import render_brief: {exc}"]

    failures = []
    for label, findings, must, must_not in RISK_FIGURE_CASES:
        rendered = render_brief.render_clinician(findings)
        for needle in must:
            if needle not in rendered:
                failures.append(f"{label}: expected {needle!r} in the output")
        for needle in must_not:
            if needle in rendered:
                failures.append(f"{label}: {needle!r} must NOT appear")
    return failures


def corpus_is_synthetic() -> list[str]:
    """
    Every fixture must announce itself as synthetic.

    This is the check that catches a real report placed in the corpus. The
    .gitignore rules can only stop git from committing one, and only by
    extension; nothing there can tell a synthetic report from a real one.
    """
    failures = []
    for path in sorted(FIXTURES.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        head = path.read_text(errors="replace")[:2000]
        if not any(marker in head for marker in SYNTHETIC_MARKERS):
            failures.append(
                f"{path.relative_to(FIXTURES)}: no synthetic marker in the first 2000 "
                "characters. If this is a real report it must not be here."
            )
    return failures


def main() -> int:
    verbose = "-v" in sys.argv
    failed = 0
    for name, spec in EXPECTED.items():
        failures = check(name, spec, verbose)
        if failures:
            failed += 1
            print(f"FAIL  {name}")
            for f in failures:
                print(f"        {f}")
        else:
            print(f"ok    {name}")

    for name, spec in SAMPLE_EXPECTED.items():
        label = f"{name} --sample {spec['sample']}"
        failures = check(name, spec, verbose)
        if failures:
            failed += 1
            print(f"FAIL  {label}")
            for f in failures:
                print(f"        {f}")
        else:
            print(f"ok    {label}")

    total = len(EXPECTED) + len(SAMPLE_EXPECTED)
    print(f"\n{total - failed}/{total} checks passed")

    print("\nIdentifier leak scan (all identifiers × all fixtures):")
    leaks = leak_scan()
    for leak in leaks:
        print(f"  LEAK  {leak}")
    print(f"  {'no leaks' if not leaks else str(len(leaks)) + ' LEAKS — fix before shipping'}")

    print("\nIndication matching (testing-gap step):")
    indication_failures = check_indications()
    for f in indication_failures:
        print(f"  FAIL  {f}")
    print(f"  {len(INDICATION_EXPECTED) - len(indication_failures)}/{len(INDICATION_EXPECTED)} pictures routed correctly")

    print("\nSKILL.md frontmatter (upload limits):")
    frontmatter_failures, frontmatter_warnings = check_skill_frontmatter()
    for f in frontmatter_failures:
        print(f"  FAIL  {f}")
    for w in frontmatter_warnings:
        print(f"  warn  {w}")
    if not frontmatter_failures:
        print("  within name/description limits")

    print("\nRisk-figure gates (render_brief.py):")
    figure_failures = check_risk_figures()
    for f in figure_failures:
        print(f"  FAIL  {f}")
    print(f"  {len(RISK_FIGURE_CASES) - len({f.split(':')[0] for f in figure_failures})}"
          f"/{len(RISK_FIGURE_CASES)} gate cases held")

    print("\nPanel, audience boundary and tier vocabulary:")
    panel_failures = check_panel()
    for f in panel_failures:
        print(f"  FAIL  {f}")
    print(f"  {len(PANEL_CASES) - len({f.split(':')[0] for f in panel_failures})}"
          f"/{len(PANEL_CASES)} panel cases held")

    print("\nSynthetic-corpus check:")
    unmarked = corpus_is_synthetic()
    for u in unmarked:
        print(f"  UNMARKED  {u}")
    print(f"  {'all fixtures marked synthetic' if not unmarked else 'UNMARKED FILES PRESENT'}")

    if failed:
        print("\nA failure means the parser changed. Read the diff before editing "
              "expectations — the fixture may be right and the parser wrong.")
    return 1 if (failed or leaks or unmarked or indication_failures
                 or figure_failures or panel_failures or frontmatter_failures) else 0


if __name__ == "__main__":
    raise SystemExit(main())
