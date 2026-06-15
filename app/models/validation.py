from pydantic import BaseModel
from enum import Enum


class Severity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    node_id: str | None = None
    severity: Severity
    code: str
    field: str | None = None
    message: str


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = []