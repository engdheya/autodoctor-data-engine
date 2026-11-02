"""Quote classification: a test verb alone must never make a sentence a procedure."""

from __future__ import annotations

import pytest

from autodoctor_data_engine.reporting.quote_classify import CATEGORIES, classify_quote, summarise

CASES = [
    (
        "A quick test is to swap coil or plug with a neighbouring cylinder and see whether "
        "the misfire moves.",
        "diagnostic_check",
    ),
    (
        "Measure the resistance at the sensor connector with a multimeter.",
        "diagnostic_check",
    ),
    (
        "the description follows CARB's monitoring requirement and Saab's diagnosis of the "
        "same pump, which recommends a wiggle test of the connector.",
        "diagnostic_check",
    ),
    (
        "GM feeds a 20 kHz test signal into the circuit and detects an open circuit when it "
        "does not cancel out, setting the code in the first trip;",
        "monitoring_description",
    ),
    (
        "The module monitors the pedal value and sets the code when both tracks disagree.",
        "monitoring_description",
    ),
    (
        "P0A37 tests whether the generator temperature reading is believable.",
        "monitoring_description",
    ),
    (
        "Ford does not use P0780-P0784 (its shift completion check feeds the solenoid codes).",
        "technical_explanation",
    ),
    (
        "For orientation, GM checks the whole pack with P0ABB to P0ABD, including a comparison "
        "of the pack voltage with the sum of all cells.",
        "technical_explanation",
    ),
    ("P0259 means its circuit reads high or draws too much current.", "technical_explanation"),
    ("The check engine light comes on after two driving cycles.", "non_procedure"),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_classification(text: str, expected: str) -> None:
    assert classify_quote(text)["category"] == expected


def test_every_result_carries_its_rule() -> None:
    result = classify_quote("Measure the voltage at pin 2 with a multimeter.")
    assert result["category"] in CATEGORIES
    assert result["rule"]
    assert result["matched"]


def test_manufacturer_as_actor_is_never_a_procedure() -> None:
    # "GM checks ..." describes the OEM strategy, not an action for the technician.
    result = classify_quote("GM checks the stored counters at every start and compares them.")
    assert result["category"] != "diagnostic_check"


def test_summary_counts_every_quote() -> None:
    counts = summarise([case[1] for case in CASES])
    assert sum(counts.values()) == len(CASES)
    assert set(counts) == set(CATEGORIES)
