"""Identity module boundary."""

from facechain.identity.exceptions import (
    IdentityError,
    InputValidationError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
)
from facechain.identity.service import FakeFaceScanner, IdentityService

__all__ = [
    "FakeFaceScanner",
    "IdentityError",
    "IdentityService",
    "InputValidationError",
    "MultipleFacesDetectedError",
    "NoFaceDetectedError",
]
