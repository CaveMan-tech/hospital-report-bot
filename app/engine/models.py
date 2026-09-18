"""Shared data models. One source of truth for the AI contract, storage and API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

EXTRACTION_VERSION = "2026-09-19.1"

# Language codes are defined by each country pack (e.g. "en", "pcm"), so this is not an enum.
Language = str
Category = Literal["emergency_refused", "detention", "abuse", "neglect", "other"]
Department = Literal[
    "emergency", "maternity", "paediatrics", "outpatient", "ward",
    "pharmacy", "lab", "records", "other", "unknown",
]
IncidentTiming = Literal["ongoing", "today", "this_week", "this_month", "older", "unknown"]
AiSeverity = Literal["severe", "not_severe", "uncertain"]
Severity = Literal["severe", "not_severe"]
ReporterRole = Literal["patient", "relative", "witness", "staff", "unknown"]
SafetyHandoff = Literal["none", "sexual_violence", "self_harm", "other_violence"]
PatientGroup = Literal["newborn", "child", "adult", "pregnant", "elderly", "unknown"]
HarmOutcome = Literal["none", "condition_worsened", "death", "unknown"]
TimeBucket = Literal["day", "night", "weekend", "unknown"]
# Country-neutral. Each pack says what the buckets mean in its own currency.
AmountBucket = Literal["small", "medium", "large", "very_large", "unknown"]
Channel = Literal["web", "whatsapp", "telegram"]
ReportStatus = Literal["new", "resolved", "unchanged", "worse", "left", "no_response"]
Credibility = Literal["ok", "review", "excluded"]
MissingField = Literal["hospital", "department", "when"]

SUBTYPES: dict[str, tuple[str, ...]] = {
    "emergency_refused": ("deposit_demanded", "no_bed_space", "no_staff", "other"),
    "detention": ("patient_held", "body_held"),
    "abuse": ("verbal", "physical", "humiliation", "other"),
    "neglect": ("left_unattended", "staff_absent", "calls_ignored", "other"),
    "other": ("other",),
}


def normalise_subtype(category: str, subtype: str) -> str:
    """Subtype must belong to its category; anything else collapses to a safe default."""
    allowed = SUBTYPES.get(category, ("other",))
    if subtype in allowed:
        return subtype
    return "other" if "other" in allowed else allowed[0]


class Extraction(BaseModel):
    """What the AI is allowed to return. It classifies and extracts, nothing else."""

    language: Language = "en"
    category: Category = "other"
    category_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    secondary_categories: list[Category] = Field(default_factory=list)
    hospital_name_raw: str | None = None
    department: Department = "unknown"
    incident_timing: IncidentTiming = "unknown"
    is_ongoing: bool | None = None
    critical_condition: bool = False
    severity: AiSeverity = "uncertain"
    reporter_role: ReporterRole = "unknown"
    patient_group: PatientGroup = "unknown"
    subtype: str = "other"
    harm_outcome: HarmOutcome = "unknown"
    time_bucket: TimeBucket = "unknown"
    money_demanded: bool | None = None
    amount_bucket: AmountBucket = "unknown"
    clinical_complaint: bool = False
    safety_handoff: SafetyHandoff = "none"
    implausible: bool = False
    is_nonsense: bool = False
    summary_redacted: str = ""
    ack: str = ""
    missing_fields: list[MissingField] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


class Hospital(BaseModel):
    id: str
    pack: str = "ng-lagos"
    name: str
    aliases: list[str] = Field(default_factory=list)
    area: str | None = None
    facility_type: Literal["general", "teaching", "specialist", "phc", "private"] = "general"


class Report(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    ref_code_hmac: str
    created_at: datetime = Field(default_factory=_now)
    channel: Channel = "web"
    pack: str = "ng-lagos"
    language: Language = "en"
    hospital_id: str | None = None
    hospital_name_raw: str | None = None
    department: Department = "unknown"
    category: Category
    secondary_categories: list[Category] = Field(default_factory=list)
    severity: Severity
    incident_timing: IncidentTiming = "unknown"
    is_ongoing: bool | None = None
    reporter_role: ReporterRole = "unknown"
    patient_group: PatientGroup = "unknown"
    subtype: str = "other"
    harm_outcome: HarmOutcome = "unknown"
    time_bucket: TimeBucket = "unknown"
    money_demanded: bool | None = None
    amount_bucket: AmountBucket = "unknown"
    extra: dict[str, Any] = Field(default_factory=dict)
    extraction_version: str = EXTRACTION_VERSION
    summary_redacted: str = ""
    rights_shown: list[str] = Field(default_factory=list)
    escalation_shown: bool = False
    followup_opt_in: bool = False
    followup_due_at: datetime | None = None
    status: ReportStatus = "new"
    credibility: Credibility = "ok"
    dedupe_key: str | None = None
    is_sample: bool = False


class Followup(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    report_id: str
    created_at: datetime = Field(default_factory=_now)
    status: Literal["resolved", "unchanged", "worse", "left"]


SESSION_TTL = timedelta(hours=2)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    channel: Channel = "web"
    pack: str = "ng-lagos"
    state: str = "S1"
    context: dict[str, Any] = Field(default_factory=dict)
    report_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    expires_at: datetime = Field(default_factory=lambda: _now() + SESSION_TTL)

    @property
    def expired(self) -> bool:
        return _now() >= self.expires_at


class EngineReply(BaseModel):
    """What every channel adapter receives back from the engine."""

    session_id: str
    replies: list[str]
    state: str
    ref_code: str | None = None
    done: bool = False
