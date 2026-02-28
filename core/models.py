from __future__ import annotations
"""
Fluidoracle — Pydantic Request/Response Models
"""
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=2000)


class VoteRequest(BaseModel):
    direction: str = Field(..., pattern="^(up|down)$")


class CommentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    is_correction: bool = False
    author_name: str = Field(default="Anonymous", max_length=100)


class ConsultSessionRequest(BaseModel):
    title: str = Field(default="New Consultation", max_length=100)


class ConsultMessageRequest(BaseModel):
    content: str = Field(default="", max_length=10000)
    force_transition: bool = False


class ConsultFeedbackRequest(BaseModel):
    rating: str = Field(..., pattern="^(positive|negative)$")
    comment: str = Field(default="", max_length=5000)


class ConsultOutcomeRequest(BaseModel):
    followup_stage: str = Field(default="user_initiated")
    implementation_status: str | None = None
    performance_rating: int | None = Field(default=None, ge=1, le=5)
    performance_notes: str | None = Field(default=None, max_length=5000)
    failure_occurred: bool = False
    failure_mode: str | None = Field(default=None, max_length=2000)
    failure_timeline: str | None = None
    operating_conditions_matched: bool | None = None
    operating_conditions_notes: str | None = Field(default=None, max_length=2000)
    modifications_made: str | None = Field(default=None, max_length=2000)
    would_recommend_same: bool | None = None
    alternative_tried: str | None = Field(default=None, max_length=2000)
    additional_notes: str | None = Field(default=None, max_length=5000)


class ConsultOutcomeUpdateRequest(BaseModel):
    implementation_status: str | None = None
    performance_rating: int | None = Field(default=None, ge=1, le=5)
    performance_notes: str | None = Field(default=None, max_length=5000)
    failure_occurred: bool | None = None
    failure_mode: str | None = Field(default=None, max_length=2000)
    failure_timeline: str | None = None
    operating_conditions_matched: bool | None = None
    operating_conditions_notes: str | None = Field(default=None, max_length=2000)
    modifications_made: str | None = Field(default=None, max_length=2000)
    would_recommend_same: bool | None = None
    alternative_tried: str | None = Field(default=None, max_length=2000)
    additional_notes: str | None = Field(default=None, max_length=5000)


class AuthSendCodeRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)


class AuthVerifyCodeRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    code: str = Field(..., min_length=6, max_length=6)


class ClaimSessionsRequest(BaseModel):
    session_ids: list[str]


class KnowledgeUpdateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    domains: list[str] | None = None
    topics: list[str] | None = None


class InventAuthRequest(BaseModel):
    passphrase: str


class InventSessionRequest(BaseModel):
    title: str = Field(default="New Session", max_length=100)


class InventMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


# ===========================================================================
