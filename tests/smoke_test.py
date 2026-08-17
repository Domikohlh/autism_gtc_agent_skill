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
]

# fixture -> expected structure.
#   genes/cnvs/repeats : ordered lists of the identifying field
#   date               : the report date the parser must choose
#   classes            : classification per variant, in order
#   must_flag          : substrings that must appear somewhere in warnings
#   must_not_contain   : substrings that must NOT appear anywhere in the JSON
EXPECTED: dict[str, dict] = {
    "01_exome_block_pten_chd8.txt": {
        "date": "12 March 2026", "test_type": "exome",
        "genes": ["PTEN", "CHD8"], "classes": ["Pathogenic", "VUS"],
        "must_flag": ["Secondary/incidental findings referenced"],
        "must_not_contain": ["7781204", "04/09/2017", "MCG-2026-004411"],
    },
    "02_exome_column_scn2a.txt": {
        # The classification column sits to the LEFT of the variant here.
        "date": "09 February 2026", "test_type": "exome",
        "genes": ["SCN2A"], "classes": ["Pathogenic"],
        "must_flag": ["read from text preceding its variant"],
        "must_not_contain": ["5540982", "17/11/2019"],
    },
    "03_cma_iscn_22q11.txt": {
        "date": "02 May 2026", "test_type": "microarray",
        "cnvs": [("22q11.21", "deletion", 1)],
        "must_not_contain": ["3391077", "22/05/2021"],
    },
    "04_cma_prose_16p11_dup.txt": {
        # Must NOT also report the reciprocal deletion the text mentions.
        "date": "18 June 2026", "test_type": "microarray",
        "cnvs": [("16p11.2", "duplication", None)],
        "must_not_contain": ["4470221", "30/01/2015"],
    },
    "05_results_page_cacna1c.txt": {
        "date": None, "test_type": None,
        "genes": ["CACNA1C"], "classes": ["Pathogenic"],
        "must_flag": ["Report date not identified", "Test type not identified"],
    },
    "06_repeat_fmr1_full_mutation.txt": {
        "date": "28 May 2026",
        "repeats": [("FMR1", "CGG", [340], "full mutation", "fully methylated")],
        "must_flag": ["Repeat expansion result present"],
        "must_not_contain": ["6620144", "08/07/2019"],
    },
    "07_negative_exome_2019_stale.txt": {
        "date": "21 October 2019", "test_type": "exome",
        "genes": [], "cnvs": [], "repeats": [],
        "must_flag": ["No variants, CNVs or repeat expansions detected"],
    },
    "08_negative_cma_recent.txt": {
        "date": "16 March 2026", "test_type": "microarray",
        "genes": [], "cnvs": [], "repeats": [],
        "must_flag": ["No variants, CNVs or repeat expansions detected"],
    },
    "09_vus_only_syngap1.txt": {
        "date": "30 January 2026", "test_type": "panel",
        "genes": ["SYNGAP1"], "classes": ["VUS"],
    },
    "10_vus_in_tier1_gene_pten.txt": {
        "date": "11 May 2026", "test_type": "exome",
        "genes": ["PTEN"], "classes": ["VUS"],
    },
    "11_secondary_finding_brca2.txt": {
        "date": "04 March 2026", "test_type": "genome",
        "genes": ["SHANK3", "BRCA2"], "classes": ["Pathogenic", "Pathogenic"],
        "must_flag": ["Secondary/incidental findings referenced"],
    },
    "12_panel_scn1a_dravet.txt": {
        "date": "14 July 2026", "test_type": "panel",
        "genes": ["SCN1A"], "classes": ["Pathogenic"],
    },
    "13_uncurated_gene_tbr1.txt": {
        "date": "06 February 2026", "test_type": "exome",
        "genes": ["TBR1"], "classes": ["Pathogenic"],
    },
    "14_multi_finding_ranking.txt": {
        "date": "01 April 2026", "test_type": "exome",
        "genes": ["ADNP", "NRXN1", "PTEN"],
        "classes": ["VUS", "VUS", "Pathogenic"],
    },
    "15_mecp2_rett.txt": {
        "date": "03 June 2026",
        "genes": ["MECP2"], "classes": ["Pathogenic"],
    },
    "16_transcript_mismatch.txt": {
        # The parser cannot know the transcript belongs to another gene. It
        # reports what the document says; catching this is the agent's job.
        "date": "20 May 2026", "test_type": "exome",
        "genes": ["SCN2A"], "classes": ["Pathogenic"],
    },
    "17_name_in_prose.txt": {
        # Documented limit: the name is in running prose and IS NOT redacted.
        "date": "24 February 2026", "test_type": "exome",
        "genes": ["ARID1B"], "classes": ["Pathogenic"],
    },
    "18_non_english_german.txt": {
        # German labels: the report date is found and the Geburtsdatum excluded,
        # but classification and zygosity are missed and must be flagged.
        "date": "27.03.2026",
        "genes": ["STXBP1"], "classes": [None],
        "must_not_contain": ["15/02/2019"],
    },
    "19_fmr1_premutation_child.txt": {
        "date": "22 April 2026",
        "repeats": [("FMR1", "CGG", [30, 78], "premutation", "unmethylated")],
        "must_flag": ["Repeat expansion result present"],
    },
    "20_mosaic_tsc2.txt": {
        "date": "09 March 2026", "test_type": "genome",
        "genes": ["TSC2"], "classes": ["Pathogenic"],
    },
    "25_prompt_injection.txt": {
        # The parser has no opinion on the injected text; it extracts the finding.
        "date": "30 April 2026", "test_type": "exome",
        "genes": ["SYNGAP1"], "classes": ["Pathogenic"],
    },
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
    "26_negative_repeat_limitation.txt": {
        # "repeat expansion", singular, inside a negation in the limitations
        # paragraph. Must NOT become a repeat record, and the negative report
        # must keep its "nothing detected" warning.
        "date": "05 February 2026", "test_type": "exome",
        "genes": [], "cnvs": [], "repeats": [],
        "must_flag": ["No variants, CNVs or repeat expansions detected"],
        "must_not_contain": ["9902311", "16/04/2017"],
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
    if "cnvs" in spec:
        cmp("cnvs", [(c["band"], c["kind"], c["copies"]) for c in record["cnvs"]], spec["cnvs"])
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

    print("\nSynthetic-corpus check:")
    unmarked = corpus_is_synthetic()
    for u in unmarked:
        print(f"  UNMARKED  {u}")
    print(f"  {'all fixtures marked synthetic' if not unmarked else 'UNMARKED FILES PRESENT'}")

    if failed:
        print("\nA failure means the parser changed. Read the diff before editing "
              "expectations — the fixture may be right and the parser wrong.")
    return 1 if (failed or leaks or unmarked or indication_failures) else 0


if __name__ == "__main__":
    raise SystemExit(main())
