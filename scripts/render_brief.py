#!/usr/bin/env python3
"""
Assemble the two-register output document from a structured findings JSON.

Writes the family-facing section first, a page break, then the clinician-facing
section — so the clinician half can be printed and handed over intact.

The content is yours to write; this script only handles structure, ordering,
de-identification checks, and the closing limits block that must appear in both.

Input JSON shape (all keys optional except `finding_summary`):

{
  "finding_summary": "...",
  "family": {
    "what_was_found": "...",
    "what_this_means": "...",
    "what_this_does_not_mean": "...",
    "tier1_monitoring": "...",
    "tier2_awareness": "...",
    "where_to_find_others": "...",
    "questions": ["...", "..."]
  },
  "clinician": {
    "finding_table": {"Gene": "PTEN", "Classification": "Pathogenic"},
    "gene_disease_association": "...",
    "variant_evidence": "...",
    "tier1_surveillance": "...",
    "tier2_associations": "...",
    "management_considerations": "...",
    "secondary_findings": "...",
    "uncertainty": "...",
    "testing_gaps": "...",
    "further_testing": "...",
    "next_steps": "...",
    "sources": [{"text": "...", "url": "...", "retrieved": "2026-08-16"}]
  },
  "urgent": ["Cardiac conduction involvement — prompt cardiology input"]
}

Usage:
    python render_brief.py findings.json --out brief.md
    python render_brief.py findings.json --html brief.html --audience family
    python render_brief.py findings.json --html clin.html --audience clinician
    python render_brief.py findings.json --family-only

`risk_figures` is optional. These are PUBLISHED PENETRANCE FIGURES FOR A NAMED
COHORT — not a score, and not this person's risk. Nothing here is computed,
combined, averaged, or adjusted; the script draws citations to scale. See
references/risk_layer_policy.md.

Every entry needs all five of `condition`, `percent` (0-100, as printed in the
source), `cohort`, `source` and `retrieved` (YYYY-MM-DD). An entry missing any
one is not drawn — it is listed underneath with the reason, because a bar is read
as a fact and an uncited number on a chart is the most persuasive way this tool
could mislead someone.

The whole block is gated on the REPORTING LABORATORY's classification, read from
clinician.finding_table. Pathogenic and likely pathogenic draw; a VUS, a benign
call, a conflicting call, or no classification recorded refuses the block and
prints why on the page. A penetrance figure beside a VUS turns "we do not know"
into a coloured bar.

  "clinician": {"finding_table": {"Classification": "Pathogenic"}},
  "risk_figures": [
    {"condition": "Thyroid cancer, lifetime", "percent": 35,
     "cohort": "PHTS patients ascertained on clinical criteria, n=3399",
     "source": "PHTS Consensus, Clin Cancer Res 2025", "retrieved": "2026-08-18"}
  ]

THE FIGURES ARE CLINICIAN-REGISTER ONLY. They appear in the clinician markdown
register and on `--audience clinician` HTML. They appear in NO family-facing
output in any format: a penetrance figure is read by a professional against the
cohort it came from, and handed to a family it reads as a forecast. Both
surfaces carry a "reference only, not a diagnosis, seek a clinician" block.

For several findings in one report, or two cohorts for one condition, use
`risk_panel` instead. It drives an interactive panel in the HTML — profile tabs
and a cohort-basis toggle, built from radio inputs and CSS so the page still has
no scripts. NOTHING IN IT IS COMPUTED: there is no score slot and no penetrance
dial. The tabs switch which finding you are reading; the toggle switches which
PUBLISHED cohort figure you are reading. `risk_figures` above is wrapped into a
single-finding panel automatically, so both shapes take the same code path.

  "risk_panel": {"findings": [{
     "label": "BRCA1 c.190T>C",
     "locus": "17q21.31",                  # schematic ideogram only, not a coordinate
     "classification": "Pathogenic",       # gated per finding, exactly as above
     "provenance": {"stars": 2, "submitters": 4, "conflicts": false,
                    "last_evaluated": "2026-05-14"},   # retrieved, never derived
     "surveillance_tier": 1,               # 1, 2 or 3 — the EVIDENCE tier from
                                           # risk_layer_policy.md. Not an
                                           # actionability or risk verdict
     "figures": [{..., "basis": "clinic"}, {..., "basis": "population"}]
  }]}

`basis` is "clinic", "population", or absent. Two or more distinct bases for one
finding raise the cohort toggle; one basis renders without it.
"""

from __future__ import annotations


import argparse
import json
import re
import sys
from pathlib import Path

try:
    from phi import find_identifiers
except ImportError:  # imported as a module from outside scripts/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phi import find_identifiers

LIMITS_BLOCK = (
    "> **What this document is and isn't.** This summarises published information "
    "about this genetic finding. It is not medical advice, not a diagnosis, and not "
    "a prediction. Every decision belongs with the clinical team — bring this to them."
)


def check_deidentified(text: str) -> list[str]:
    """
    Identifier shapes still present in the assembled document.

    Uses the same ruleset as the parser (phi.py). This check used to keep its own
    shorter list, which meant a brief carrying a date of birth, a hospital
    number, a lab email and a specimen ID passed untouched — the script writing
    the document handed to a clinic had the weakest check in the repository.
    """
    return find_identifiers(text)


# Advisory checks on the family half only. Testing showed it drifting long,
# technical and tutorial — definitions nobody asked for, citations mid-sentence,
# a teaching voice. These flag the drift; they never block, because a term is
# occasionally the right call and only the writer can tell.
CITATION_SHAPES = [
    # Any parenthetical ending in a year: "(Cage et al., 2024)", "(Brain, 2024)",
    # "(International PHTS Consensus, 2025)". All three are the same drift.
    (re.compile(r"\([^)\n]{3,60},\s*(?:19|20)\d{2}\)"), "parenthetical citation"),
    (re.compile(r"\*[^*\n]{3,60}\*,?\s*\d{4}"), "italicised journal name with a year"),
    (re.compile(r"\b\d{4};\s*\d+\(\d+\)"), "volume/issue citation"),
    (re.compile(r"https?://|\bdoi:", re.IGNORECASE), "URL or DOI"),
    (re.compile(r"\b(?:PMID|GeneReviews|ClinGen|ClinVar|OMIM|ACMG)\b"), "database or body named inline"),
]

# The jargon list is the plain-language glossary — one source, so the check and
# the translation cannot drift apart. Terms marked `keep` are excluded: a family
# needs the name of their own test, and flagging it would be noise.
def _load_jargon() -> list[str]:
    path = Path(__file__).resolve().parent.parent / "assets" / "plain_language.json"
    try:
        terms = json.loads(path.read_text())["terms"]
    except (OSError, ValueError, KeyError):
        return []
    return [t for t, e in terms.items() if not e.get("keep")]


JARGON = _load_jargon()

FAMILY_WORD_LIMIT = 800


def check_family_register(text: str) -> list[str]:
    """Advisory notes on plainness of the family half. Never blocks."""
    notes = []
    for pattern, label in CITATION_SHAPES:
        if pattern.search(text):
            notes.append(f"{label} in the family half — evidence belongs in the clinician section")
    found = [term for term in JARGON if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)]
    if found:
        notes.append(
            "technical terms in the family half: " + ", ".join(sorted(set(found)))
            + " — replace with what each means in practice rather than defining it"
        )
    words = len(text.split())
    if words > FAMILY_WORD_LIMIT:
        notes.append(
            f"family half is {words} words (target under {FAMILY_WORD_LIMIT}) — a shorter "
            "brief that gets read beats a complete one that does not"
        )
    return notes


def section(title: str, body: str | None, level: int = 2) -> str:
    """Render a section, or nothing at all if the body is empty."""
    if not body or not str(body).strip():
        return ""
    return f"{'#' * level} {title}\n\n{str(body).strip()}"


def assemble(blocks: list[str]) -> str:
    """
    Join complete blocks with exactly one blank line between them.

    Each block is self-contained, so an omitted section leaves no trace — no run
    of blank lines where it would have been, and no heading butted up against
    the block above it, which Markdown would not render as a heading at all.
    """
    return "\n\n".join(b.strip() for b in blocks if b and b.strip()) + "\n"


def quote_block(title: str, items: list[str]) -> str:
    return "\n".join([f"> **{title}**", ">"] + [f"> - {item}" for item in items])


def render_family(data: dict) -> str:
    # `or {}` rather than a default: a key present but null is a normal shape
    # out of a partial pipeline, and should render an empty section, not crash.
    fam = data.get("family") or {}
    out = ["# Understanding this genetic result"]

    summary = data.get("finding_summary")
    if summary and str(summary).strip():
        out.append(f"_{str(summary).strip()}_")

    if data.get("urgent"):
        out.append(quote_block("Please raise these with a doctor promptly:", data["urgent"]))

    out.append(section("What was found", fam.get("what_was_found")))
    out.append(section("What this means", fam.get("what_this_means")))
    out.append(section("What this does not mean", fam.get("what_this_does_not_mean")))
    out.append(section("Health monitoring that goes with this finding", fam.get("tier1_monitoring")))
    out.append(section("Things worth knowing about", fam.get("tier2_awareness")))
    out.append(section("Where to find others", fam.get("where_to_find_others")))

    questions = fam.get("questions") or []
    if questions:
        out.append(
            "## Questions to bring to your next appointment\n\n"
            + "\n".join(f"- {q}" for q in questions)
        )

    out.append(LIMITS_BLOCK)
    return assemble(out)


def render_clinician(data: dict) -> str:
    clin = data.get("clinician") or {}
    out = ["# Genomic result summary — clinician section"]

    summary = data.get("finding_summary")
    if summary and str(summary).strip():
        out.append(f"_{str(summary).strip()}_")

    if data.get("urgent"):
        out.append(quote_block("Time-critical:", data["urgent"]))

    table = clin.get("finding_table") or {}
    if table:
        rows = "\n".join(
            f"| {k} | {v if v not in (None, '') else '—'} |" for k, v in table.items()
        )
        out.append("## Finding\n\n| Field | Value |\n|---|---|\n" + rows)

    out.append(section("Gene–disease association", clin.get("gene_disease_association")))
    out.append(section("Variant-level evidence — ClinVar / OMIM", clin.get("variant_evidence")))
    out.append(section("Established surveillance — Tier 1", clin.get("tier1_surveillance")))
    out.append(section("Documented associations without formal protocol — Tier 2", clin.get("tier2_associations")))
    out.append(section("Management considerations", clin.get("management_considerations")))

    # Figures live in the clinician register of the markdown document, because
    # that is the half carrying the sources they have to be read against.
    out.append(risk_figures_markdown(data)[0])

    out.append(section("Secondary findings", clin.get("secondary_findings")))
    out.append(section("Uncertainty and limitations", clin.get("uncertainty")))
    # The testing-gap pair sits in this register deliberately: it is follow-up
    # for whoever can act on it, and noise in the family half.
    out.append(section("Testing performed, and what it could not detect",
                       clin.get("testing_gaps")))
    out.append(section("Further testing indicated", clin.get("further_testing")))
    out.append(section("Suggested next steps", clin.get("next_steps")))

    sources = clin.get("sources") or []
    if sources:
        lines = []
        for i, s in enumerate(sources, 1):
            line = f"{i}. {s.get('text', '')}"
            if s.get("url"):
                line += f" — {s['url']}"
            if s.get("retrieved"):
                line += f" _(retrieved {s['retrieved']})_"
            lines.append(line)
        out.append("## Sources\n\n" + "\n".join(lines))
    else:
        out.append(
            "## Sources\n\n_No sources recorded. This is a problem — every clinical "
            "assertion above needs a source and a retrieval date._"
        )

    out.append(LIMITS_BLOCK)
    return assemble(out)


# --------------------------------------------------------------------------
# Interactive HTML output
# --------------------------------------------------------------------------

HTML_STYLE = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;padding:1.5rem 1rem 4rem;max-width:44rem;margin-inline:auto;
 font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,sans-serif;
 color:#1a1a1a;background:#fdfdfc}
h1{font-size:1.55rem;line-height:1.25;margin:0 0 .3rem}
.sub{color:#555;margin:0 0 2rem}
h2{font-size:1.12rem;margin:2rem 0 .6rem}
p,li{margin:0 0 .8rem}ul{padding-left:1.2rem}
.urgent{border-left:4px solid #b3261e;background:#fdf0ef;padding:.9rem 1rem;
 border-radius:4px;margin:0 0 1.8rem}
.urgent strong{color:#b3261e}
details{border:1px solid #e0ddd8;border-radius:6px;padding:.7rem .9rem;margin:0 0 .8rem;
 background:#fff}
summary{cursor:pointer;font-weight:600}
.chart{border:1px solid #e0ddd8;border-radius:6px;padding:1rem;margin:0 0 1rem;background:#fff}
.src{font-size:.85rem;color:#555;margin:.15rem 0 .9rem}
.limits{margin-top:2.5rem;padding:1rem;border:1px solid #e0ddd8;border-radius:6px;
 background:#fbfaf8;font-size:.95rem;color:#444}
@media(prefers-color-scheme:dark){
 body{color:#e8e6e3;background:#16161a}.sub,.src{color:#a8a5a0}
 details,.chart{background:#1e1e23;border-color:#33323a}
 .urgent{background:#2a1a19}.limits{background:#1c1c21;border-color:#33323a;color:#b8b5b0}}
@media print{body{max-width:none}details{border:none}details summary{list-style:none}}
"""


# Panel styling, kept out of the shared stylesheet and emitted only on the page
# that actually carries a panel. The family page then contains none of this
# machinery at all — not the rules, not the class names, not a comment about
# cohorts — rather than merely containing no figures.
PANEL_STYLE = """
.refonly,.refused{border-left:4px solid #8a6d1f;background:#fdf9ec;padding:.8rem .95rem;
 border-radius:4px;color:#4a3d1a}
.refonly{margin:0 0 1rem;font-size:.93rem}
.vpr,.abr{position:absolute;opacity:0;width:0;height:0;pointer-events:none}
.vpbody,.abbody{display:none}.abonly{display:block}
.vptabs{display:flex;gap:.25rem;background:#efece7;border-radius:9px;padding:.25rem;
 margin:0 0 1.1rem;flex-wrap:wrap}
.vptabs label{flex:1 1 8rem;text-align:center;padding:.5rem .6rem;border-radius:7px;
 cursor:pointer;font-size:.9rem;font-weight:600}
.abtabs{display:flex;gap:.25rem;align-items:center;margin:0 0 .8rem;flex-wrap:wrap}
.abtabs label{padding:.35rem .8rem;border-radius:99px;cursor:pointer;font-size:.85rem;
 border:1px solid #d5d1c9}
.ablead{font-size:.8rem;letter-spacing:.04em;text-transform:uppercase;color:#666;
 margin-right:.4rem}
.stats{display:flex;gap:1rem;flex-wrap:wrap;border-top:1px solid #e0ddd8;
 border-bottom:1px solid #e0ddd8;padding:.9rem 0;margin:0 0 1.1rem}
.stats div{flex:1 1 9rem}
.stats span{display:block;font-size:.8rem;color:#666;margin-bottom:.15rem}
.stats .cls{font-size:1.02rem}
.cls-blocked{color:#8a6d1f}
.basisnote{font-size:.85rem;color:#555;margin:0 0 .7rem}
.bodycap{display:none}
@media(prefers-color-scheme:dark){
 .refonly,.refused{background:#241f12;color:#e0d4ad;border-color:#a8862b}
 .vptabs{background:#26262c}.abtabs label{border-color:#3d3c45}
 .stats{border-color:#33323a}.stats span,.basisnote,.ablead{color:#a8a5a0}
 .cls-blocked{color:#d9b45a}}
@media print{
 /* A printed record must be complete: every tab and every cohort basis, each
    captioned so the reader knows which finding they are looking at. */
 .vpbody,.abbody{display:block !important}
 .vptabs,.abtabs{display:none}
 .bodycap{display:block;font-weight:600;margin:1.2rem 0 .4rem}}
"""


def esc(x) -> str:
    return (str(x).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def html_body(text: str) -> str:
    """Paragraphs, preserving any '- ' list."""
    out, bullets = [], []
    for line in str(text).strip().splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ")):
            bullets.append(f"<li>{esc(line[2:])}</li>"); continue
        if bullets:
            out.append("<ul>" + "".join(bullets) + "</ul>"); bullets = []
        if line:
            out.append(f"<p>{esc(line)}</p>")
    if bullets:
        out.append("<ul>" + "".join(bullets) + "</ul>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Published risk figures
#
# Penetrance figures published for a named cohort. NOT a score for the person in
# front of you: nothing below computes, combines, averages or adjusts anything.
# A score describes a person and would be a prediction; these describe cohorts
# and are citations. references/risk_layer_policy.md is the governing document,
# and the checks here are its enforcement.
# --------------------------------------------------------------------------

RETRIEVED_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Checked BEFORE the pathogenic test, so "likely benign" cannot pass on the
# strength of the word "likely".
BLOCKING_CLASSIFICATION = (
    "uncertain", "vus", "benign", "conflict", "unknown", "class 3",
    "not provided", "none", "not reported",
)

REFERENCE_ONLY = (
    "Reference only. These are published research findings, reproduced with their "
    "sources. They are not a diagnosis, not a risk assessment for this patient, and "
    "not a basis for a clinical decision on their own. Interpretation belongs with a "
    "clinical genetics professional — direct the patient to their genetics team or an "
    "appropriately qualified clinician for guidance."
)

# The figures are a clinician-register artefact and appear in no family-facing
# output, in any format. A penetrance figure is read by a professional against
# the cohort it came from; handed to a family it reads as a forecast, and no
# amount of caption survives that.
FIGURES_AUDIENCE = "clinician"

FIGURE_CAPTION = (
    "Each figure is the published penetrance for the cohort named beside it — not a "
    "score, not a prediction, and not this person's risk. Cohorts ascertained through "
    "an already-affected relative run systematically higher than population-based ones."
)


def classification_verdict(value: str) -> tuple[bool, str]:
    """
    The gate itself, given a classification string.

    One implementation, applied per finding by the panel and by the markdown
    tables alike, so two surfaces cannot drift into disagreeing about the same
    variant. The value comes from the reporting laboratory and is never inferred.
    """
    value = str(value or "").strip()
    if not value:
        return False, (
            "no classification recorded in the finding table. Figures are gated on the "
            "reporting laboratory's classification and are not drawn without it"
        )

    low = value.lower()
    for word in BLOCKING_CLASSIFICATION:
        if word in low:
            return False, (
                f"the reported classification is '{value}'. A variant not established as "
                "causal carries no risk figure — see references/risk_layer_policy.md, Tier 3"
            )
    if low.startswith(("pathogenic", "likely pathogenic")):
        return True, ""
    return False, (
        f"the reported classification '{value}' was not recognised as pathogenic or "
        "likely pathogenic. Figures are refused rather than guessed at"
    )


def figure_problems(fig) -> list[str]:
    """Every reason this entry cannot be drawn. An empty list means it can."""
    if not isinstance(fig, dict):
        return ["entry is not an object"]

    problems = []
    if not str(fig.get("condition") or "").strip():
        problems.append("no condition named")

    pct = fig.get("percent")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        problems.append("percent is not a number")
    elif not 0 <= float(pct) <= 100:
        # This used to clamp into range, which turned a typed 350 into a
        # full-width bar with no warning — a silent failure in the worst
        # possible direction. Out of range is now a refusal.
        problems.append(f"percent {pct} is outside 0-100")

    if not str(fig.get("cohort") or "").strip():
        problems.append(
            "no cohort recorded (a figure without the population it was measured in "
            "reads as this person's own risk)"
        )
    if not str(fig.get("source") or "").strip():
        problems.append("no source")
    if not RETRIEVED_DATE.match(str(fig.get("retrieved") or "")):
        problems.append("no retrieval date in YYYY-MM-DD form")
    return problems


def partition_figures(figures: list) -> tuple[list, list[str]]:
    """Split into drawable figures and one refusal line per rejected entry."""
    ok, rejected = [], []
    for fig in figures:
        problems = figure_problems(fig)
        if problems:
            name = (fig.get("condition") if isinstance(fig, dict) else None) or "(unnamed)"
            rejected.append(f"{name}: {'; '.join(problems)}")
        else:
            ok.append(fig)
    return ok, rejected


def _cell(value) -> str:
    """One markdown table cell: pipes escaped, newlines flattened."""
    return " ".join(str(value).split()).replace("|", "\\|")


def risk_figures_markdown(data: dict) -> tuple[str, list[str]]:
    """
    The same findings, the same gates, rendered as tables. Returns (md, notes).

    Reads through panel_findings() so the markdown and the interactive panel
    cannot disagree about a variant: one normalisation, one gate, two surfaces.
    """
    findings = panel_findings(data)
    if not findings:
        return "", []

    notes: list[str] = []
    blocks = ["## Published figures for this condition",
              f"> **Reference only.** {REFERENCE_ONLY.split('. ', 1)[1]}"]

    for finding in findings:
        label = str(finding.get("label") or "This finding").strip()
        classification = str(finding.get("classification") or "").strip()
        blocks.append(f"### {label}")

        meta = [f"ACMG classification: **{classification or 'not recorded'}**"]
        prov = provenance_label(finding.get("provenance"))
        if prov:
            meta.append(f"Evidence provenance: {prov}")
        tier_text, tier_note = tier_label(finding.get("surveillance_tier"))
        if tier_note:
            notes.append(f"{label}: {tier_note}")
        if tier_text:
            meta.append(f"Surveillance tier: {tier_text}")
        blocks.append(" · ".join(meta))

        allowed, reason = classification_verdict(classification)
        if not allowed:
            blocks.append(f"**No figures are shown.** {reason[0].upper() + reason[1:]}.")
            notes.append(f"{label}: figures refused — {reason}")
            continue

        ok, rejected = partition_figures(finding.get("figures") or [])
        for line in rejected:
            notes.append(f"{label}: not drawn — {line}")

        grouped: dict[str, list] = {}
        for fig in ok:
            grouped.setdefault(normalise_basis(fig.get("basis")), []).append(fig)
        bases = [b for b in BASIS_ORDER if grouped.get(b)]

        if ok:
            blocks.append(FIGURE_CAPTION)
        for b in bases:
            if len(bases) > 1:
                blocks.append(f"**{BASIS_LABELS[b]}** — {BASIS_NOTES[b]}")
            rows = "\n".join(
                f"| {_cell(f['condition'])} | {float(f['percent']):g}% | {_cell(f['cohort'])} "
                f"| {_cell(f['source'])} | {_cell(f['retrieved'])} |" for f in grouped[b])
            blocks.append(
                "| Condition | Published figure | Measured in | Source | Retrieved |\n"
                "|---|---|---|---|---|\n" + rows)
        if rejected:
            blocks.append(
                "**Not shown — the entry did not carry what a figure needs:**\n\n"
                + "\n".join(f"- {r}" for r in rejected))

    return "\n\n".join(blocks), notes


# --------------------------------------------------------------------------
# The interactive figure panel (clinician register only)
#
# Same shape as a variant-browser UI — profile tabs, a locus schematic, a
# fan-out to conditions — with one deliberate difference: NOTHING IS COMPUTED.
# There is no score slot and no penetrance dial. The slot where a calculator
# would put a derived number holds retrieved ClinVar provenance instead, and
# the control that would adjust a person's parameters instead switches between
# two PUBLISHED figures for different cohorts. Every interaction changes which
# citation you are reading, never what a number works out to.
#
# No <script>: the tabs are radio inputs and `:checked ~` sibling rules, so the
# page still opens offline, prints, and survives being emailed.
# --------------------------------------------------------------------------

CYTOBAND_FULL = re.compile(r"^(\d{1,2}|[XY])([pq])(\d{1,2})(?:\.\d+)?$", re.IGNORECASE)

TIER_LABELS = {
    "1": "Tier 1 — published surveillance protocol",
    "2": "Tier 2 — documented, no protocol",
    "3": "Tier 3 — excluded",
}

# The mock this panel is modelled on carried "Clinical Actionability: Tier III
# (Low Risk)". That is an actionability call and a risk verdict, neither of
# which this skill makes (guardrail 9). The vocabulary is therefore closed to
# the three EVIDENCE tiers in risk_layer_policy.md, and anything else is
# refused rather than printed.
def tier_label(tier) -> tuple[str, str]:
    """(label, note-if-unusable) for the surveillance-tier slot."""
    if tier in (None, "", []):
        return "", ""
    key = str(tier).strip().lower().removeprefix("tier").strip()
    key = {"i": "1", "ii": "2", "iii": "3"}.get(key, key)
    if key in TIER_LABELS:
        return TIER_LABELS[key], ""
    return "", (f"surveillance tier {tier!r} is not one of the three evidence tiers "
                "(1, 2, 3) — it was not printed. This slot carries the evidence tier "
                "from risk_layer_policy.md, not an actionability or risk verdict")


def provenance_label(prov) -> str:
    """
    The evidence-provenance slot, assembled from what was actually retrieved.

    Whatever is missing is simply absent — this slot exists to show how well
    supported the laboratory's classification is, and padding it out would
    defeat that. Empty means nothing was retrieved, which is itself the answer.
    """
    if not isinstance(prov, dict):
        return ""
    bits = []
    stars = prov.get("stars")
    if isinstance(stars, int) and 0 <= stars <= 4:
        bits.append("★" * stars + "☆" * (4 - stars))
    subs = prov.get("submitters")
    if isinstance(subs, int) and subs >= 0:
        bits.append(f"{subs} submitter" + ("s" if subs != 1 else ""))
    if "conflicts" in prov:
        bits.append("conflicting calls" if prov["conflicts"] else "no conflicts")
    if prov.get("last_evaluated"):
        bits.append(f"last evaluated {prov['last_evaluated']}")
    return " · ".join(bits)


def band_position(cytoband: str) -> tuple[float, str] | None:
    """
    Where to draw the highlight on a schematic chromosome, as a height fraction.

    Cytoband numbers increase with distance from the centromere, so the ORDER of
    two bands on one arm is a real fact and the drawing respects it. The exact
    position is NOT retrieved and is not claimed: the ideogram is captioned as a
    schematic, and no coordinate is asserted anywhere in the output.
    """
    m = CYTOBAND_FULL.match(str(cytoband or "").strip())
    if not m:
        return None
    arm, major = m.group(2).lower(), int(m.group(3))
    reach = min(major / 25.0, 1.0)
    if arm == "p":
        return 0.40 - reach * 0.36, "p"
    return 0.50 + reach * 0.44, "q"


def ideogram_svg(cytoband: str, accent: str) -> str:
    """A schematic chromosome with the reported band marked. Not to scale."""
    # Everything is currentColor at low opacity so the schematic reads correctly
    # in both themes. Hardcoded light fills turned the chromosome into a glaring
    # white bar on the dark page.
    x, y, w, h = 14, 16, 24, 190
    parts = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
             f'fill="currentColor" opacity=".13"/>']
    for frac in (0.10, 0.22, 0.62, 0.80):
        parts.append(f'<rect x="{x}" y="{y + h*frac:.0f}" width="{w}" height="9" '
                     f'fill="currentColor" opacity=".26"/>')
    parts.append(f'<ellipse cx="{x + w/2}" cy="{y + h*0.455:.0f}" rx="{w/2}" ry="7" '
                 f'fill="currentColor" opacity=".2"/>')
    pos = band_position(cytoband)
    if pos:
        frac, _ = pos
        parts.append(f'<rect x="{x-3}" y="{y + h*frac:.0f}" width="{w+6}" height="11" '
                     f'rx="3" fill="{accent}"/>')
    return "".join(parts)


def fanout_svg(figures: list, cytoband: str, accent: str) -> str:
    """
    Locus → variant → one bubble per condition, each bubble a published figure.

    The viewBox is sized to the 44rem text column rather than to a wide canvas:
    an SVG scaled down to fit takes its type down with it, and a 9px axis label
    in a clinical document is a defect, not a style.

    Condition names are budgeted and truncated here; the full name, the cohort,
    the source and the retrieval date all sit in the list beneath, which wraps.
    Truncating a label is safe precisely because nothing depends on it — the
    cohort statement, which must never be shortened, is never inside the SVG.
    """
    n = len(figures)
    height = max(226, n * 74 + 56)
    mid = height / 2
    pos = band_position(cytoband)
    locus_y = 16 + 190 * (pos[0] if pos else 0.5)
    hub_x, bub_x, label_x = 200, 330, 368

    out = [ideogram_svg(cytoband, accent)]
    out.append('<text x="26" y="220" font-size="10" fill="currentColor" opacity=".6" '
               'text-anchor="middle">schematic</text>')

    # Decorative strand between locus and hub. It asserts nothing and is hidden
    # from assistive technology rather than read out as meaningless geometry.
    for i in range(9):
        sy = mid - 68 + i * 17
        out.append(f'<circle cx="{112 + (i % 2) * 20}" cy="{sy:.0f}" r="3.2" '
                   f'fill="currentColor" opacity=".22" aria-hidden="true"/>')
        out.append(f'<circle cx="{132 - (i % 2) * 20}" cy="{sy:.0f}" r="3.2" '
                   f'fill="currentColor" opacity=".22" aria-hidden="true"/>')

    out.append(f'<path d="M44 {locus_y:.0f} C96 {locus_y:.0f} 150 {mid:.0f} '
               f'{hub_x} {mid:.0f}" fill="none" stroke="{accent}" stroke-width="2" '
               f'stroke-dasharray="5 4"/>')
    out.append(f'<circle cx="{hub_x}" cy="{mid:.0f}" r="6" fill="{accent}"/>')

    for i, f in enumerate(figures):
        by = 42 + i * 74 + (height - (n * 74 + 4)) / 2
        pct = float(f["percent"])
        name = str(f["condition"])
        shown = name if len(name) <= 30 else name[:29].rstrip() + "…"
        out.append(f'<path d="M{hub_x+6} {mid:.0f} C{hub_x+64} {mid:.0f} '
                   f'{bub_x-64} {by:.0f} {bub_x-26} {by:.0f}" fill="none" '
                   f'stroke="{accent}" stroke-width="2" stroke-dasharray="5 4"/>')
        out.append(f'<circle cx="{bub_x}" cy="{by:.0f}" r="25" fill="none" '
                   f'stroke="{accent}" stroke-width="2.5"/>')
        out.append(f'<text x="{bub_x}" y="{by+5:.0f}" font-size="14" font-weight="600" '
                   f'text-anchor="middle" fill="currentColor">{pct:g}%</text>')
        out.append(f'<text x="{label_x}" y="{by+5:.0f}" font-size="13.5" '
                   f'fill="currentColor">{esc(shown)}</text>')

    label = "; ".join(f'{esc(f["condition"])} {float(f["percent"]):g} per cent'
                      for f in figures)
    return (f'<svg viewBox="0 0 620 {height}" width="100%" role="img" '
            f'aria-label="Published penetrance by condition: {label}">'
            + "".join(out) + "</svg>")



BASIS_ORDER = ("clinic", "population", "unspecified")
BASIS_LABELS = {
    "clinic": "Clinic-ascertained",
    "population": "Population-based",
    "unspecified": "Cohort as published",
}
BASIS_NOTES = {
    "clinic": ("Measured in families that came to attention through an already-affected "
               "relative. Systematically higher than the population figure."),
    "population": ("Measured in carriers identified without regard to family history — "
                   "the closer comparison for a variant found incidentally."),
    "unspecified": "Ascertainment not recorded separately; the cohort is named per figure.",
}


def normalise_basis(value) -> str:
    """Map a figure's `basis` onto the closed vocabulary."""
    low = str(value or "").strip().lower()
    if not low:
        return "unspecified"
    if low.startswith("clinic") or "ascertain" in low:
        return "clinic"
    if low.startswith("pop"):
        return "population"
    return "unspecified"


def panel_findings(data: dict) -> list[dict]:
    """
    One list of findings for the panel, whichever shape the caller used.

    `risk_panel.findings` drives it when present. Otherwise the flat
    `risk_figures` list is wrapped into a single finding using the finding
    table — so the older shape keeps working and there is still only one
    renderer to reason about.
    """
    panel = data.get("risk_panel") or {}
    if isinstance(panel, dict) and isinstance(panel.get("findings"), list):
        return [f for f in panel["findings"] if isinstance(f, dict)]

    figures = data.get("risk_figures") or []
    if not figures:
        return []
    table = (data.get("clinician") or {}).get("finding_table") or {}
    label, classification = "", ""
    for key, val in table.items():
        k = str(key).lower()
        if "classification" in k:
            classification = str(val if val is not None else "").strip()
        elif k in ("gene", "variant", "finding") and not label:
            label = str(val if val is not None else "").strip()
    clin = data.get("clinician") or {}
    return [{
        "label": label or "This finding",
        "locus": table.get("Locus") or table.get("Cytoband") or "",
        "classification": classification,
        "provenance": clin.get("evidence_provenance"),
        "surveillance_tier": clin.get("surveillance_tier"),
        "figures": figures,
    }]


def risk_panel_html(data: dict) -> tuple[str, list[str]]:
    """
    The interactive panel. Returns (html, notes for stderr).

    Every finding gets a tab whether or not it can show figures: a VUS tab that
    states why it is empty is more use than a finding quietly missing from the
    selector, and it is the honest answer to the question the tab poses.
    """
    findings = panel_findings(data)
    if not findings:
        return "", []

    notes: list[str] = []
    css: list[str] = []
    tabs: list[str] = []
    inputs: list[str] = []
    bodies: list[str] = []

    for i, finding in enumerate(findings):
        label = str(finding.get("label") or f"Finding {i + 1}").strip()
        locus = str(finding.get("locus") or "").strip()
        classification = str(finding.get("classification") or "").strip()
        checked = " checked" if i == 0 else ""

        inputs.append(f'<input class="vpr" type="radio" name="vp" id="vp{i}"{checked}>')
        tabs.append(f'<label for="vp{i}">{esc(label)}</label>')
        css.append(f"#vp{i}:checked ~ .vptabs label[for=vp{i}]"
                   "{background:#5B7A99;color:#fff}")
        css.append(f"#vp{i}:checked ~ #vpb{i}{{display:block}}")

        allowed, reason = classification_verdict(classification)
        body = [f'<div class="vpbody" id="vpb{i}">']

        # --- stats row: what was reported and what was retrieved, never derived
        slots = [("ACMG classification",
                  esc(classification) or "not recorded",
                  "" if allowed else " cls-blocked")]
        prov = provenance_label(finding.get("provenance"))
        if prov:
            slots.append(("Evidence provenance", esc(prov), ""))
        tier_text, tier_note = tier_label(finding.get("surveillance_tier"))
        if tier_note:
            notes.append(f"{label}: {tier_note}")
        if tier_text:
            slots.append(("Surveillance tier", esc(tier_text), ""))
        body.append('<div class="stats">' + "".join(
            f'<div><span>{s}</span><strong class="cls{c}">{v}</strong></div>'
            for s, v, c in slots) + "</div>")

        if not allowed:
            body.append('<div class="refused"><strong>No figures are shown.</strong> '
                        f'{esc(reason[0].upper() + reason[1:])}.</div>')
            notes.append(f"{label}: figures refused — {reason}")
            body.append("</div>")
            bodies.append("".join(body))
            continue

        ok, rejected = partition_figures(finding.get("figures") or [])
        for line in rejected:
            notes.append(f"{label}: not drawn — {line}")

        grouped: dict[str, list] = {}
        for fig in ok:
            grouped.setdefault(normalise_basis(fig.get("basis")), []).append(fig)
        bases = [b for b in BASIS_ORDER if grouped.get(b)]

        if len(bases) > 1:
            # The control that would have been a penetrance dial. It switches
            # between two PUBLISHED cohorts; it does not adjust a number.
            for b in bases:
                mark = " checked" if b == bases[0] else ""
                body.append(f'<input class="abr" type="radio" name="ab{i}" '
                            f'id="ab{i}_{b}"{mark}>')
                css.append(f"#ab{i}_{b}:checked ~ .abtabs label[for=ab{i}_{b}]"
                           "{background:#5B7A99;color:#fff}")
                css.append(f"#ab{i}_{b}:checked ~ #abb{i}_{b}{{display:block}}")
            body.append('<div class="abtabs"><span class="ablead">Cohort basis</span>'
                        + "".join(f'<label for="ab{i}_{b}">{BASIS_LABELS[b]}</label>'
                                  for b in bases) + "</div>")

        for b in bases:
            figs = grouped[b]
            open_tag = (f'<div class="abbody" id="abb{i}_{b}">' if len(bases) > 1
                        else '<div class="abbody abonly">')
            body.append(open_tag)
            body.append(f'<p class="bodycap">{esc(label)} — {BASIS_LABELS[b].lower()}</p>')
            if len(bases) > 1:
                body.append(f'<p class="basisnote">{esc(BASIS_NOTES[b])}</p>')
            body.append('<div class="chart">'
                        + fanout_svg(figs, locus, "#5B7A99")
                        + "".join(
                            f'<div class="src"><strong>{esc(f["condition"])}</strong> — '
                            f'{float(f["percent"]):g}%, measured in {esc(f["cohort"])}. '
                            f'{esc(f["source"])} (retrieved {esc(f["retrieved"])})</div>'
                            for f in figs)
                        + "</div>")
            body.append("</div>")

        if rejected:
            body.append("<p><strong>Not shown — the entry did not carry what a figure "
                        "needs:</strong></p><ul>"
                        + "".join(f"<li>{esc(r)}</li>" for r in rejected) + "</ul>")
        body.append("</div>")
        bodies.append("".join(body))

    html = (f"<style>{''.join(css)}</style>"
            '<div class="vpanel">' + "".join(inputs)
            + '<div class="vptabs">' + "".join(tabs) + "</div>"
            + "".join(bodies) + "</div>")
    return html, notes


def render_html(data: dict, audience: str) -> str:
    """
    One self-contained page. `audience` is "family" or "clinician".

    No script tags, no external assets, no fonts — it opens offline, prints, and
    survives being emailed.
    """
    fam = data.get("family") or {}
    clin = data.get("clinician") or {}
    title = ("Understanding this genetic result" if audience == "family"
             else "Genomic result summary — clinician")
    parts = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f"<title>{esc(title)}</title><style>{HTML_STYLE}</style></head><body>",
             f"<h1>{esc(title)}</h1>"]
    summary = (data.get("finding_summary") or "").strip()
    if summary:
        parts.append(f'<p class="sub">{esc(summary)}</p>')
    if data.get("urgent"):
        items = "".join(f"<li>{esc(u)}</li>" for u in data["urgent"])
        parts.append('<div class="urgent"><strong>Raise these with a doctor promptly'
                     f"</strong><ul>{items}</ul></div>")

    if audience == "family":
        open_ = [("What was found", "what_was_found"),
                 ("What this means", "what_this_means"),
                 ("Health monitoring that goes with this finding", "tier1_monitoring")]
        fold = [("What this does not mean", "what_this_does_not_mean"),
                ("Things worth knowing about", "tier2_awareness"),
                ("Where to find others", "where_to_find_others")]
        src = fam
    else:
        open_ = [("Gene–disease association", "gene_disease_association"),
                 ("Variant-level evidence — ClinVar / OMIM", "variant_evidence"),
                 ("Established surveillance — Tier 1", "tier1_surveillance"),
                 ("Management considerations", "management_considerations")]
        fold = [("Documented associations — Tier 2", "tier2_associations"),
                ("Uncertainty and limitations", "uncertainty"),
                ("Testing performed, and what it could not detect", "testing_gaps"),
                ("Further testing indicated", "further_testing"),
                ("Suggested next steps", "next_steps")]
        src = clin

    for label, key in open_:
        if src.get(key):
            parts.append(f"<h2>{esc(label)}</h2>\n{html_body(src[key])}")

    has_figures = bool(data.get("risk_figures") or (data.get("risk_panel") or {}).get("findings"))
    if has_figures and audience == FIGURES_AUDIENCE:
        parts.append("<h2>Published figures for this condition</h2>")
        parts.append(f'<div class="refonly"><strong>Reference only.</strong> '
                     f'{esc(REFERENCE_ONLY.split(". ", 1)[1])}</div>')
        panel, _notes = risk_panel_html(data)
        if panel:
            parts.append(f"<style>{PANEL_STYLE}</style>")
            parts.append(panel)
            parts.append(f'<p class="src">{esc(FIGURE_CAPTION)}</p>')

    for label, key in fold:
        if src.get(key):
            parts.append(f"<details><summary>{esc(label)}</summary>\n{html_body(src[key])}</details>")

    if audience == "family" and (fam.get("questions") or []):
        items = "".join(f"<li>{esc(q)}</li>" for q in fam["questions"])
        parts.append(f"<h2>Questions to bring to your next appointment</h2><ul>{items}</ul>")

    if audience == "clinician" and (clin.get("sources") or []):
        items = "".join(
            f"<li>{esc(s.get('text',''))}"
            + (f" — {esc(s['url'])}" if s.get("url") else "")
            + (f" <em>(retrieved {esc(s['retrieved'])})</em>" if s.get("retrieved") else "")
            + "</li>" for s in clin["sources"])
        parts.append(f"<h2>Sources</h2><ul>{items}</ul>")

    parts.append('<div class="limits">'
                 + esc(LIMITS_BLOCK.replace("> ", "").replace("**", "")) + "</div>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("findings", help="Structured findings JSON")
    ap.add_argument("--out", help="Write to this path (default: stdout)")
    ap.add_argument("--html", metavar="PATH",
                    help="Write a self-contained interactive page instead of markdown")
    ap.add_argument("--audience", choices=("family", "clinician"), default="family",
                    help="Which register the HTML page carries (default: family)")
    ap.add_argument("--family-only", action="store_true")
    ap.add_argument("--clinician-only", action="store_true")
    ap.add_argument(
        "--allow-phi", action="store_true",
        help="Write the file even if the PHI check finds identifiers (it will not by default)",
    )
    args = ap.parse_args()

    if args.family_only and args.clinician_only:
        ap.error("--family-only and --clinician-only are mutually exclusive; "
                 "omit both to render the two-register document")

    path = Path(args.findings)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON — {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("error: findings JSON must be an object", file=sys.stderr)
        return 1

    parts = []
    if not args.clinician_only:
        family = render_family(data)
        parts.append(family)
        for note in check_family_register(family):
            print(f"register: {note}", file=sys.stderr)
    if not args.family_only:
        parts.append(render_clinician(data))

    document = "\n\n---\n\n".join(p.strip() for p in parts) + "\n"

    # Say on stderr what the page says on paper. A refused figure that only
    # shows up buried in a rendered document is a refusal the author can miss.
    if panel_findings(data):
        for note in risk_figures_markdown(data)[1]:
            print(f"risk figures: {note}", file=sys.stderr)
        if args.family_only:
            print("risk figures: they are a clinician-register artefact and appear in "
                  "no family-facing output, so --family-only omits them entirely.",
                  file=sys.stderr)

    leaks = check_deidentified(document)
    if leaks:
        print(
            "warning: output may contain identifiable data — "
            + ", ".join(leaks)
            + ". Remove before sharing.",
            file=sys.stderr,
        )
        # A warning on stderr is easy to miss, and this document is meant to be
        # handed to a clinic. Writing the file is the step that makes the leak
        # durable, so that step is the one that stops.
        if args.out and not args.allow_phi:
            print(
                f"error: refusing to write {args.out} — remove the identifiers above, "
                "or pass --allow-phi if this is intentional.",
                file=sys.stderr,
            )
            return 1

    if args.html:
        page = render_html(data, args.audience)
        # The HTML is the most shareable thing this tool produces, so a leak in
        # it travels furthest. Same gate, refused harder.
        html_leaks = check_deidentified(page)
        if html_leaks and not args.allow_phi:
            print("error: refusing to write " + args.html + " — identifiable data ("
                  + ", ".join(html_leaks) + "). An HTML page is the most shareable "
                  "output here; a leak in it travels furthest.", file=sys.stderr)
            return 1
        Path(args.html).write_text(page)
        print(f"wrote {args.html} ({args.audience} register)")

    if args.out:
        Path(args.out).write_text(document)
        print(f"wrote {args.out}")
    elif not args.html:
        # Only fall back to stdout when nothing was written. Printing the
        # markdown alongside an HTML file is noise, not a second copy.
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())