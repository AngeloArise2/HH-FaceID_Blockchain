"""Cross-module data models. This is the shared source of truth."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class AuthorizedImage(BaseModel):
    image_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    consent_reference: str = Field(min_length=3, max_length=128)


class FaceScan(BaseModel):
    embedding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detector: str
    face_count: Literal[1]
    scanned_at: datetime


class PublicPost(BaseModel):
    source_url: HttpUrl
    platform: str
    title: str | None = None
    text_excerpt: str | None = Field(default=None, max_length=500)
    image_url: HttpUrl | None = None
    retrieved_at: datetime


class EvidenceBundle(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    consent_reference: str
    input_image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    face_embedding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: str
    post: PublicPost
