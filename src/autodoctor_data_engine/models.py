"""Typed intermediate representation shared by connectors, validators and loaders.

Raw upstream payloads are converted into these models by the connectors. The
models are the contract between the extraction layer and everything downstream,
so a new source only has to produce valid models to participate in the pipeline.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Language = str
ContextType = Literal["generic", "manufacturer", "ecu", "vehicle_variant"]
VerificationStatus = Literal["verified", "source_reported", "conflicting", "unverified"]
Likelihood = Literal["low", "medium", "high"]
Difficulty = Literal["easy", "medium", "hard", "shop_only"]


class Provenance(BaseModel):
    """Where a record came from - the anchor of the whole provenance chain."""

    source_slug: str
    source_commit: str
    file_path: str
    source_record_id: str
    raw_hash: str
    extraction_method: str = "connector"
    ingested_at: str
    modified: bool = False
    notes: str | None = None


class Context(BaseModel):
    """The context a DTC identity is valid in.

    ``generic``            - SAE J2012 / ISO 15031-6 generic OBD-II meaning
    ``manufacturer``       - manufacturer specific meaning
    ``ecu``                - meaning tied to a specific control unit
    ``vehicle_variant``    - meaning documented for one vehicle variant
    """

    type: ContextType
    manufacturer: str | None = None
    ecu: str | None = None
    vehicle_variant: str | None = None

    @model_validator(mode="after")
    def _require_target(self) -> Context:
        if self.type == "manufacturer" and not self.manufacturer:
            raise ValueError("a manufacturer context requires a manufacturer")
        if self.type == "ecu" and not self.ecu:
            raise ValueError("an ecu context requires an ecu")
        if self.type == "vehicle_variant" and not self.vehicle_variant:
            raise ValueError("a vehicle_variant context requires a vehicle_variant")
        if self.type == "generic" and (self.manufacturer or self.ecu or self.vehicle_variant):
            raise ValueError("a generic context must not carry a manufacturer/ecu/variant")
        return self


class Definition(BaseModel):
    language: Language
    title: str | None = None
    description: str | None = None

    def is_empty(self) -> bool:
        return not (self.title or "").strip() and not (self.description or "").strip()


class Cause(BaseModel):
    key: str
    likelihood: Likelihood | None = None
    labels: dict[Language, str] = Field(default_factory=dict)


class Symptom(BaseModel):
    key: str
    texts: dict[Language, str] = Field(default_factory=dict)


class Test(BaseModel):
    key: str
    kind: str = "check"
    texts: dict[Language, str] = Field(default_factory=dict)
    expected: str | None = None
    requires_tool: str | None = None


class Repair(BaseModel):
    key: str
    texts: dict[Language, str] = Field(default_factory=dict)
    difficulty: Difficulty | None = None
    diy_possible: bool | None = None
    cost_min: float | None = None
    cost_max: float | None = None
    currency: str | None = None
    hours_min: float | None = None
    hours_max: float | None = None


class Component(BaseModel):
    key: str
    labels: dict[Language, str] = Field(default_factory=dict)


class Flags(BaseModel):
    mil: bool | None = None
    emissions_relevant: bool | None = None
    drive_cycle_required: bool | None = None
    limp_mode_possible: bool | None = None
    severity_label: str | None = None


class NormalizedDtc(BaseModel):
    record_type: Literal["dtc"] = "dtc"
    code: str
    standard: str = "unknown"
    protocol: str | None = None
    category: str | None = None
    system: str | None = None
    subsystem: str | None = None
    context: Context
    definitions: list[Definition] = Field(default_factory=list)
    causes: list[Cause] = Field(default_factory=list)
    symptoms: list[Symptom] = Field(default_factory=list)
    tests: list[Test] = Field(default_factory=list)
    repairs: list[Repair] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    related_codes: list[str] = Field(default_factory=list)
    flags: Flags = Field(default_factory=Flags)
    references: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    provenance: Provenance

    @property
    def context_key(self) -> str:
        c = self.context
        if c.type == "generic":
            target = "generic"
        elif c.type == "manufacturer":
            target = (c.manufacturer or "").lower()
        elif c.type == "ecu":
            target = (c.ecu or "").lower()
        else:
            target = (c.vehicle_variant or "").lower()
        return f"{self.code}|{self.standard}|{c.type}:{target}"


class NormalizedPid(BaseModel):
    record_type: Literal["pid"] = "pid"
    mode: str
    pid: str
    scope: Literal["generic", "vehicle"] = "generic"
    bytes: int | None = None
    unit: str | None = None
    formula: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    signal_id: str | None = None
    path: str | None = None
    fmt: dict[str, Any] | None = None
    names: dict[Language, str] = Field(default_factory=dict)
    provenance: Provenance


class NormalizedVehicle(BaseModel):
    record_type: Literal["vehicle"] = "vehicle"
    manufacturer: str
    model: str
    generation: str | None = None
    year_start: int | None = None
    year_end: int | None = None
    description: str | None = None
    variant_name: str | None = None
    engine_code: str | None = None
    power_kw: float | None = None
    provenance: Provenance


class NormalizedEcu(BaseModel):
    record_type: Literal["ecu"] = "ecu"
    name: str
    vendor: str | None = None
    model: str | None = None
    variant: str | None = None
    ecu_type: str | None = None
    protocol: str | None = None
    vehicle_variant: str | None = None
    header: str | None = None
    provenance: Provenance


NormalizedRecord = NormalizedDtc | NormalizedPid | NormalizedVehicle | NormalizedEcu

_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {
    "dtc": NormalizedDtc,
    "pid": NormalizedPid,
    "vehicle": NormalizedVehicle,
    "ecu": NormalizedEcu,
}


def model_for(record_type: str) -> type[BaseModel]:
    try:
        return _MODEL_BY_TYPE[record_type]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"unknown record_type: {record_type!r}") from exc


def parse_record(payload: dict[str, Any]) -> NormalizedRecord:
    """Validate a JSONL row into the right model."""
    record_type = payload.get("record_type")
    model = model_for(record_type)
    return model.model_validate(payload)  # type: ignore[return-value]
