from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    bug = "bug"
    risk = "risk"
    missing_test = "missing_test"
    style = "style"


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Verdict(str, Enum):
    approve = "approve"
    comment = "comment"
    request_changes = "request_changes"


class Finding(BaseModel):
    category: Category
    severity: Severity
    file: str = Field(description="Path exactly as it appears in the diff")
    line: Optional[int] = Field(default=None, description="Line number in the NEW version of the file, if known")
    title: str = Field(description="One short sentence")
    explanation: str = Field(description="Why this is a problem, grounded in the diff")
    suggestion: str = Field(description="Concrete fix or test to add")
    evidence: str = Field(default="", description="Short verbatim snippet from the diff that supports the finding")
    verified: bool = Field(default=True, description="Set by the grounding check, not by the model")


class ReviewReport(BaseModel):
    summary: str
    verdict: Verdict
    findings: list[Finding]
