"""Data quality rules.

Two families:
  * record rules (run on the normalized layer, before merging)
  * database rules (run after the merge, on the SQLite file)

Every rule has a stable id, a severity and a machine readable message. Rules with
severity ``error`` that appear in :data:`BLOCKING_RULES` must produce zero failures
before a database version may be published.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from ..config import Rules
from ..models import (
    NormalizedDtc,
    NormalizedEcu,
    NormalizedPid,
    NormalizedRecord,
    NormalizedVehicle,
)
from ..normalizers.codes import DEFAULT_RULES, is_prefix_manufacturer_specific, is_valid_code
from ..normalizers.text import normalize_url
from ..utils.textsim import canonical_form

Severity = Literal["error", "warning", "info"]

#: rules whose failure blocks a release
BLOCKING_RULES: frozenset[str] = frozenset(
    {
        "V001_code_format",
        "V006_provenance_complete",
        "V007_context_integrity",
        "V009_repair_range",
        "V010_numeric_non_negative",
        "V014_pid_format",
    }
)

_HEX = re.compile(r"^[0-9A-F]+$")


@dataclass
class ValidationIssue:
    rule_id: str
    severity: Severity
    passed: bool
    message: str
    entity_type: str
    entity_key: str
    entity_id: int | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "passed": self.passed,
            "message": self.message,
            "entity_type": self.entity_type,
            "entity_key": self.entity_key,
            "entity_id": self.entity_id,
            "created_at": self.created_at,
        }


def _ok(rule_id: str, severity: Severity, entity_type: str, key: str) -> ValidationIssue:
    return ValidationIssue(rule_id, severity, True, "ok", entity_type, key)


def _fail(rule_id: str, severity: Severity, message: str, entity_type: str, key: str) -> ValidationIssue:
    return ValidationIssue(rule_id, severity, False, message, entity_type, key)


def validate_record(record: NormalizedRecord, rules: Rules | None = None) -> list[ValidationIssue]:
    """Run every record-level rule against one normalized record."""
    rules = rules or DEFAULT_RULES
    issues: list[ValidationIssue] = []
    issues.extend(_check_provenance(record))
    if isinstance(record, NormalizedDtc):
        issues.extend(_check_dtc(record, rules))
    elif isinstance(record, NormalizedPid):
        issues.extend(_check_pid(record))
    elif isinstance(record, NormalizedVehicle):
        issues.extend(_check_vehicle(record))
    elif isinstance(record, NormalizedEcu):
        issues.extend(_check_ecu(record))
    return issues


# ---------------------------------------------------------------------------
# record level rules
# ---------------------------------------------------------------------------

def _check_provenance(record: NormalizedRecord) -> list[ValidationIssue]:
    prov = record.provenance
    key = _record_key(record)
    missing = [
        name
        for name, value in (
            ("source_slug", prov.source_slug),
            ("source_commit", prov.source_commit),
            ("file_path", prov.file_path),
            ("source_record_id", prov.source_record_id),
            ("raw_hash", prov.raw_hash),
            ("ingested_at", prov.ingested_at),
        )
        if not value
    ]
    if missing:
        return [
            _fail(
                "V006_provenance_complete",
                "error",
                f"missing provenance fields: {', '.join(missing)}",
                record.record_type,
                key,
            )
        ]
    return [_ok("V006_provenance_complete", "error", record.record_type, key)]


def _check_dtc(record: NormalizedDtc, rules: Rules) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    key = record.context_key

    if not is_valid_code(record.code, rules):
        issues.append(
            _fail("V001_code_format", "error", f"invalid DTC code {record.code!r}", "dtc", key)
        )
    else:
        issues.append(_ok("V001_code_format", "error", "dtc", key))

    letter_category = {"P": "powertrain", "B": "body", "C": "chassis", "U": "network"}.get(
        record.code[:1]
    )
    if record.category and letter_category and record.category.lower() != letter_category:
        issues.append(
            _fail(
                "V002_category_consistent",
                "warning",
                f"category {record.category!r} contradicts code prefix {record.code[0]!r}",
                "dtc",
                key,
            )
        )
    else:
        issues.append(_ok("V002_category_consistent", "warning", "dtc", key))

    usable = [d for d in record.definitions if not d.is_empty()]
    if not usable:
        issues.append(_fail("V003_definition_present", "error", "no definition text", "dtc", key))
    else:
        issues.append(_ok("V003_definition_present", "error", "dtc", key))
        for definition in usable:
            text = (definition.title or "") + " " + (definition.description or "")
            if len(canonical_form(text)) < 4:
                issues.append(
                    _fail(
                        "V004_definition_meaningful",
                        "warning",
                        f"{definition.language}: definition text is too short",
                        "dtc",
                        key,
                    )
                )
                break
        else:
            issues.append(_ok("V004_definition_meaningful", "warning", "dtc", key))

    languages = [d.language for d in record.definitions]
    if len(languages) != len(set(languages)):
        issues.append(
            _fail("V005_language_unique", "warning", "duplicate language in one record", "dtc", key)
        )
    else:
        issues.append(_ok("V005_language_unique", "warning", "dtc", key))

    bad_languages = [lang for lang in languages if not re.fullmatch(r"[a-z]{2}", lang or "")]
    if bad_languages:
        issues.append(
            _fail("V017_language_code", "warning", f"bad language code(s): {bad_languages}", "dtc", key)
        )
    else:
        issues.append(_ok("V017_language_code", "warning", "dtc", key))

    ctx = record.context
    if ctx.type == "manufacturer" and not ctx.manufacturer:
        issues.append(
            _fail("V007_context_integrity", "error", "manufacturer context without manufacturer",
                  "dtc", key)
        )
    elif ctx.type == "generic" and record.standard == "manufacturer_specific":
        issues.append(
            _fail(
                "V007_context_integrity",
                "error",
                "manufacturer specific standard stored in a generic context",
                "dtc",
                key,
            )
        )
    else:
        issues.append(_ok("V007_context_integrity", "error", "dtc", key))

    for related in record.related_codes:
        if related == record.code:
            issues.append(
                _fail("V011_related_self_reference", "warning", f"{record.code} relates to itself",
                      "dtc", key)
            )
            break
        if not is_valid_code(related, rules):
            issues.append(
                _fail("V008_related_format", "warning", f"invalid related code {related!r}", "dtc", key)
            )
            break
    else:
        issues.append(_ok("V008_related_format", "warning", "dtc", key))

    range_problem = None
    for repair in record.repairs:
        for low, high, name in (
            (repair.cost_min, repair.cost_max, "cost"),
            (repair.hours_min, repair.hours_max, "hours"),
        ):
            if low is not None and high is not None and low > high:
                range_problem = f"{name} min {low} > max {high}"
                break
        if range_problem:
            break
    if range_problem:
        issues.append(_fail("V009_repair_range", "error", range_problem, "dtc", key))
    else:
        issues.append(_ok("V009_repair_range", "error", "dtc", key))

    negative = [
        value
        for repair in record.repairs
        for value in (repair.cost_min, repair.cost_max, repair.hours_min, repair.hours_max)
        if value is not None and value < 0
    ]
    if negative:
        issues.append(
            _fail("V010_numeric_non_negative", "error", f"negative estimate: {negative}", "dtc", key)
        )
    else:
        issues.append(_ok("V010_numeric_non_negative", "error", "dtc", key))

    if is_prefix_manufacturer_specific(record.code) and record.context.type == "generic":
        issues.append(
            _fail(
                "V020_prefix_scope_mismatch",
                "warning",
                f"{record.code} has a manufacturer-specific prefix (second character 1) but the "
                "source files it in the generic (all-vehicles) layer",
                "dtc",
                key,
            )
        )
    else:
        issues.append(_ok("V020_prefix_scope_mismatch", "warning", "dtc", key))

    if record.standard == "unknown":
        issues.append(
            _fail("V012_standard_known", "warning", "standard could not be inferred", "dtc", key)
        )
    else:
        issues.append(_ok("V012_standard_known", "warning", "dtc", key))

    if record.code.startswith("U") is False and re.fullmatch(rules.uds_code_pattern, record.code) \
            and record.protocol == "obd2":
        issues.append(
            _fail("V013_uds_with_obd_context", "warning", "UDS code declared as OBD-II", "dtc", key)
        )

    bad_urls = []
    for url in record.evidence_urls:
        normalized = normalize_url(url)
        if not normalized or not normalized.startswith(("http://", "https://")):
            bad_urls.append(url)
    if bad_urls:
        issues.append(
            _fail("V016_evidence_url", "warning", f"suspicious evidence URLs: {bad_urls[:3]}",
                  "dtc", key)
        )
    else:
        issues.append(_ok("V016_evidence_url", "warning", "dtc", key))

    return issues


def _check_pid(record: NormalizedPid) -> list[ValidationIssue]:
    key = f"{record.mode}.{record.pid}.{record.signal_id or ''}"
    problems = []
    if not re.fullmatch(r"[0-9A-F]{2}", record.mode or ""):
        problems.append(f"mode {record.mode!r} is not two hex digits")
    if not _HEX.match(record.pid or ""):
        problems.append(f"pid {record.pid!r} is not hex")
    if problems:
        return [_fail("V014_pid_format", "error", "; ".join(problems), "pid", key)]
    issues = [_ok("V014_pid_format", "error", "pid", key)]
    if not record.names:
        issues.append(_fail("V015_pid_named", "warning", "PID has no name", "pid", key))
    if record.range_min is not None and record.range_max is not None \
            and record.range_min > record.range_max:
        issues.append(
            _fail("V009_repair_range", "error", "range min > max", "pid", key)
        )
    return issues


def _check_vehicle(record: NormalizedVehicle) -> list[ValidationIssue]:
    key = f"{record.manufacturer}/{record.model}/{record.generation or ''}"
    problems = []
    if not record.manufacturer or not record.model:
        problems.append("manufacturer or model missing")
    if record.year_start and record.year_end and record.year_start > record.year_end:
        problems.append(f"year_start {record.year_start} > year_end {record.year_end}")
    for year in (record.year_start, record.year_end):
        if year is not None and not (1900 <= year <= 2100):
            problems.append(f"implausible model year {year}")
    if problems:
        return [_fail("V018_vehicle_integrity", "error", "; ".join(problems), "vehicle", key)]
    return [_ok("V018_vehicle_integrity", "error", "vehicle", key)]


def _check_ecu(record: NormalizedEcu) -> list[ValidationIssue]:
    key = record.name
    if not record.name or len(record.name.strip()) < 2:
        return [_fail("V019_ecu_integrity", "error", "ECU name missing", "ecu", key)]
    return [_ok("V019_ecu_integrity", "error", "ecu", key)]


def _record_key(record: NormalizedRecord) -> str:
    if isinstance(record, NormalizedDtc):
        return record.context_key
    if isinstance(record, NormalizedPid):
        return f"{record.mode}.{record.pid}.{record.signal_id or ''}"
    if isinstance(record, NormalizedVehicle):
        return f"{record.manufacturer}/{record.model}/{record.generation or ''}"
    return record.name


def blockable_errors(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if not i.passed and i.rule_id in BLOCKING_RULES]


def summarize(issues: list[ValidationIssue]) -> dict[str, int]:
    summary = {"total": len(issues), "passed": 0, "failed": 0, "errors": 0, "warnings": 0}
    for issue in issues:
        if issue.passed:
            summary["passed"] += 1
            continue
        summary["failed"] += 1
        if issue.severity == "error":
            summary["errors"] += 1
        elif issue.severity == "warning":
            summary["warnings"] += 1
    return summary
