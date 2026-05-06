from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ApplianceSymptomsDTO(BaseModel):
    appliance_type: str
    problem_description: str
    started_at: Optional[str] = Field(
        default=None, description="Free-form when the issue began (e.g. '2 days ago')."
    )
    error_codes: List[str] = Field(default_factory=list)
    sounds: List[str] = Field(default_factory=list)
    observed_behavior: List[str] = Field(default_factory=list)
    recent_changes: Optional[str] = None


class DiagnosticStepDTO(BaseModel):
    order: int = Field(..., ge=1)
    title: str
    instruction: str
    safety_warning: Optional[str] = None
    expected_outcome: Optional[str] = None


class DiagnosticReportDTO(BaseModel):
    appliance_type: str
    likely_causes: List[str] = Field(default_factory=list)
    severity: str = Field(default="medium", description="low|medium|high|critical")
    recommended_steps: List[DiagnosticStepDTO] = Field(default_factory=list)
    requires_technician: bool = False
    technician_reason: Optional[str] = None


class VisionAnalysisDTO(BaseModel):
    detected_appliance: Optional[str] = None
    visible_issues: List[str] = Field(default_factory=list)
    error_indicators: List[str] = Field(default_factory=list)
    severity_estimate: str = "medium"
    summary: str
