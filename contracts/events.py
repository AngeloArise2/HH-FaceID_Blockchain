"""Pipeline observability contract; never include biometric/raw image data."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class PipelineEvent(BaseModel):
    run_id: str
    stage: Literal["validated", "face_scanned", "post_found", "anchored", "verified", "failed"]
    occurred_at: datetime
    detail: str | None = None
