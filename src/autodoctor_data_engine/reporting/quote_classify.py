"""Classify a quoted source sentence: is it a diagnostic check, or just prose?

The client's objection was correct: a sentence that mentions a test verb is not automatically
an inspection procedure. Most of them describe how the control unit monitors a signal, explain
how the system works, or mention the check-engine lamp. This module sorts every quote into one
of four categories with deterministic rules and keeps the matched evidence, so the review
count never inflates the number of procedures and a reviewer can audit every label.

Categories (first matching rule wins):

``diagnostic_check``
    An action performed **on the vehicle by a person**: an imperative or obligation form
    ("measure the…", "should be checked", "a quick test is to…", "wiggle test") that names
    hardware, an instrument or a measurement.
``monitoring_description``
    How the control unit decides to store the code: "is set when", "detects", "monitors",
    "plausibility", "checks whether the value is believable".
``technical_explanation``
    Explains the system or the code family: "means", "is a", "documented", "does not use".
``non_procedure``
    Anything else: coverage notes, caveats, references.

A statement whose actor is the manufacturer or the module is never a diagnostic check, even
when it contains "checks" or "measures" - that is how the OEM's strategy works, not what a
technician does.
"""

from __future__ import annotations

import re
from typing import Any

CATEGORIES = (
    "diagnostic_check",
    "monitoring_description",
    "technical_explanation",
    "non_procedure",
)

# Forms that ask a person to act.
ACTION_PATTERNS: tuple[str, ...] = (
    r"\btest is to\b",
    r"\bquick test\b",
    r"\bwiggle test\b",
    r"\bshould be (?:tested|checked|measured|inspected|probed)\b",
    r"\bmust be (?:tested|checked|measured|inspected)\b",
    r"\bcan be (?:tested|checked|measured|probed)\b",
    r"\bto (?:test|check|measure|verify|inspect)\b",
    r"\b(?:test|check|measure|probe|inspect|disconnect|swap|relearn)\s+(?:the|a|both|each|all)\b",
    r"\bread (?:out|the)\b",
    r"\bcompare the\b",
    r"^\s*(?:test|check|measure|probe|inspect|swap|disconnect|read|verify)\b",
    r"\bperform (?:a|an|the)\b[^.]{0,40}\b(?:test|check|measurement)\b",
)

HARDWARE_OBJECTS = (
    "wiring",
    "harness",
    "connector",
    "plug",
    "sensor",
    "voltage",
    "resistance",
    "continuity",
    "pressure",
    "signal",
    "ground",
    "supply",
    "pin",
    "coil",
    "injector",
    "spark plug",
    "valve",
    "motor",
    "fuse",
    "battery",
)

INSTRUMENTS = (
    "multimeter",
    "oscilloscope",
    "scan tool",
    "scan-tool",
    "diagnostic tool",
    "gauge",
    "breakout box",
    "test lamp",
    "smoke machine",
)

# The module or the OEM as the actor: strategy description, never a technician action.
# Descriptive quantifiers: a sentence that starts like this is explaining a family of engines,
# not telling a technician what to do.
DESCRIPTIVE_OPENING = re.compile(
    r"^\s*(?:some|most|many|modern|older|all|several|a few|on some|on many|in some)\b",
    re.IGNORECASE,
)

ACTOR_NOT_PERSON = re.compile(
    r"\b(?:the\s+)?(?:module|ecu|control unit|unit|system|processor|software|"
    r"gm|ford|vw|volkswagen|toyota|lexus|subaru|mazda|saab|honda|acura|bmw|"
    r"mercedes|audi|hyundai|kia|nissan|renault|peugeot|citroen|fiat|volvo|"
    r"chrysler|dodge|jeep|chevrolet|buick|cadillac|gmc|mitsubishi|suzuki|jaguar|"
    r"land rover|porsche|tesla|opel|vauxhall|seat|skoda|"
    r"engines?|diesels?|vehicles?|makers?|manufacturers?|modules?|sensors?|"
    r"systems?|pumps?|valves?|actuators?|ecm|tcm|bcm|pcm|inverter|charger)\b\s+"
    r"(?:checks?|tests?|monitors?|measures?|compares?|detects?|calculates?)",
    re.IGNORECASE,
)

MONITORING_PATTERNS: tuple[str, ...] = (
    r"\bis set when\b",
    r"\bstored when\b",
    r"\bsets? the code\b",
    r"\bthe module\b",
    r"\bmonitors?\b",
    r"\bmonitored\b",
    r"\bdetects?\b",
    r"\bplausibility\b",
    r"\brationality\b",
    r"\bbelievable\b",
    r"\b(?:checks?|tests?) whether\b",
    r"\bevaluates?\b",
    r"\bcounts?\b",
    r"\bthreshold\b",
)

EXPLANATION_PATTERNS: tuple[str, ...] = (
    r"\bmeans\b",
    r"\bis an?\b",
    r"\bare\b",
    r"\bdocumented\b",
    r"\bdoes not use\b",
    r"\bnot use\b",
    r"\bexamples?\b",
    r"\bbecause\b",
    r"\bso that\b",
    r"\bwhich allows\b",
    r"\bconsists\b",
    r"\bworks\b",
    r"\bfor orientation\b",
    r"\bfollows\b",
)

MEASUREMENT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:%|V|mV|A|mA|ohm|Ω|kΩ|bar|hPa|psi|kPa|°C|C|rpm|km/h|mm|s|Hz|kHz)\b"
)


def _matched(text: str, patterns: tuple[str, ...]) -> list[str]:
    hits = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            hits.append(match.group(0).strip())
    return hits


def _contains(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if re.search(rf"\b{re.escape(term)}\b", lowered)]


def classify_quote(text: str) -> dict[str, Any]:
    """Return the category plus the evidence that produced it."""
    actions = _matched(text, ACTION_PATTERNS)
    objects = _contains(text, HARDWARE_OBJECTS)
    instruments = _contains(text, INSTRUMENTS)
    measurements = [m.group(0) for m in MEASUREMENT.finditer(text)]
    actor_is_not_person = bool(ACTOR_NOT_PERSON.search(text)) or bool(
        DESCRIPTIVE_OPENING.match(text)
    )
    monitoring = _matched(text, MONITORING_PATTERNS)
    explanation = _matched(text, EXPLANATION_PATTERNS)

    if actions and (instruments or objects or measurements) and not actor_is_not_person:
        return {
            "category": "diagnostic_check",
            "rule": "imperative/obligation test form + hardware, instrument or measurement",
            "matched": (actions + instruments + objects + measurements)[:8],
        }
    if monitoring:
        return {
            "category": "monitoring_description",
            "rule": "control-unit or code-setting vocabulary",
            "matched": monitoring[:8],
        }
    if explanation:
        return {
            "category": "technical_explanation",
            "rule": "explanatory vocabulary",
            "matched": explanation[:8],
        }
    return {
        "category": "non_procedure",
        "rule": "no imperative test form, monitoring marker or explanation marker",
        "matched": [],
    }


def summarise(categories: list[str]) -> dict[str, int]:
    counts = {category: 0 for category in CATEGORIES}
    for category in categories:
        counts[category] = counts.get(category, 0) + 1
    return counts
