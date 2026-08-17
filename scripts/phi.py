#!/usr/bin/env python3
"""
Identifier patterns, shared by the parser and the renderer.

One ruleset, two uses:

  - `redact()`          — parse_report.py, to strip identifiers from a report
                          before anything is extracted from it
  - `find_identifiers()` — render_brief.py, to refuse to write a document that
                          still carries any

These lived separately, and drifted: the renderer knew about five identifier
shapes and the parser about eight, so a brief containing a date of birth, a
hospital number, a lab email and a specimen ID passed the renderer's gate
untouched. The script guarding the document that gets handed to a clinic had
the weaker check. Keeping one list is the fix.

Rule order matters. Labelled identifiers are removed first, so that by the time
the name rules run, a following "DOB:" or "MRN:" has already become a bracketed
placeholder and cannot be mistaken for another word of the name.

Nothing here consumes to end of line. Contexts are whitespace-joined before
these run, so a greedy rule would eat the variant along with the identifier.
"""

from __future__ import annotations

import re

# Date formats, shared with the parser's own date handling. Kept here because
# the date-of-birth rule needs it and this module must not import upwards.
DATE_SRC = (
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"  # the dotted form is standard across Europe
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
)

# One to four capitalised words on a single line, none of which is itself a
# field label. With `\s*` between tokens the match runs past the end of the line
# and swallows the NEXT field's label 

_NAME_TOKENS = r"(?:(?![\w'’\-]+[ \t]*[:：])[A-Z][\w'’\-]*,?[ \t]*){1,4}"

# (pattern, replacement, human label for reporting)
RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(?:d\.?o\.?b\.?|date\s+of\s+birth|birth\s*date|geburtsdatum"
                rf"|fecha\s+de\s+nacimiento|date\s+de\s+naissance)\s*[:：]?\s*(?:{DATE_SRC})",
                re.IGNORECASE),
     "[DOB REDACTED]", "date of birth"),

    # Labs name this field a dozen ways; matching only "MRN" leaks the rest.
    # The value must contain a digit, or "Referral number: see below" redacts
    # the word "see" and prose values get eaten.
    (re.compile(r"\b(?:MRN|(?:medical\s+record|hospital|record|chart|case|lab(?:oratory)?"
                r"|patient|episode|referral)\s*(?:no\.?|number|id|#)"
                r"|patient\s*id"
                r"|fallnummer|patientennummer|aktenzeichen"
                r"|n(?:ú|u)mero\s+de\s+historia|num(?:é|e)ro\s+de\s+dossier)"
                r"\s*[:：#]?[ \t]*(?=[\w-]*\d)[\w-]+", re.IGNORECASE),
     "[RECORD NUMBER REDACTED]", "record or hospital number"),

    (re.compile(r"\bNHS\s*(?:no\.?|number)?\s*[:：]?\s*\d[\d ]{8,12}", re.IGNORECASE),
     "[NHS NUMBER REDACTED]", "NHS number"),

    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
     "[SSN REDACTED]", "SSN-shaped string"),

    # The value must contain a digit, or this eats the specimen TYPE — and
    # "Specimen: peripheral blood" vs "fibroblast" vs "saliva" is clinically
    # load-bearing: it governs how a mosaic result is interpreted and whether
    # RNA testing on that tissue would be informative. Redacting an accession
    # number is required; redacting the tissue destroys evidence.
    (re.compile(r"\b(?:accession|specimen|sample)\s*(?:no\.?|number|id|#)?\s*[:：#][ \t]*"
                r"(?=[A-Z0-9\-]*\d)[A-Z0-9][A-Z0-9\-]{3,}", re.IGNORECASE),
     "[ACCESSION REDACTED]", "lab accession number"),

    # Multi-label domains need the repeated group, or lab@genomics.nhs.uk
    # redacts to "[EMAIL REDACTED].uk".
    (re.compile(r"\b[\w.\-]+@[\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]{2,}\b"),
     "[EMAIL REDACTED]", "email address"),

    # "Gene name:" is a real field on many reports, so only `patient` triggers
    # the name rule mid-line; a bare "Name:" is only honoured at line start.
    (re.compile(r"\b(?:patient(?:'s)?(?:\s+name)?|pt\.?\s+name)\s*[:：][ \t]*"
                + _NAME_TOKENS, re.IGNORECASE),
     "[NAME REDACTED] ", "patient name"),

    (re.compile(r"(?:^|\n)[ \t]*name\s*[:：][ \t]*" + _NAME_TOKENS, re.IGNORECASE),
     "\n[NAME REDACTED] ", "name field"),
]


def redact(text: str) -> str:
    """
    Strip labelled identifiers from a document.

    Applied to the WHOLE document at the input boundary, before any parsing, so
    that no context window can ever be cut in a way that separates an identifier
    from the label that identifies it. Redacting extracted windows instead leaks
    the value whenever the window slices through its label — which is exactly
    what a short report does.
    """
    for pattern, replacement, _label in RULES:
        text = pattern.sub(replacement, text)
    return text


def find_identifiers(text: str) -> list[str]:
    """
    Return the labels of any identifier shapes present, in rule order.

    The placeholders `redact()` leaves behind are inert here: every rule
    requires a date, a digit, an `@`, or a capitalised name token, and
    "[DOB REDACTED]" has none of them.
    """
    return [label for pattern, _replacement, label in RULES if pattern.search(text)]
