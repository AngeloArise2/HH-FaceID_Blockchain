"""Identity module boundary."""

from facechain.identity.exceptions import (
    IdentityError,
    InputValidationError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    RecognitionUnavailableError,
)
from facechain.identity.provider import InsightFaceFaceScanner
from facechain.identity.service import FakeFaceScanner, IdentityService

__all__ = [
    "FakeFaceScanner",
    "IdentityError",
    "IdentityService",
    "InputValidationError",
    "InsightFaceFaceScanner",
    "MultipleFacesDetectedError",
    "NoFaceDetectedError",
    "RecognitionUnavailableError",
]