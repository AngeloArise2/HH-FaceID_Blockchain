"""Identity module exceptions."""


class IdentityError(Exception):
    """Base exception for all identity module errors."""


class InputValidationError(IdentityError):
    """Raised when the input image fails validation (missing, unreadable, bad hash)."""


class NoFaceDetectedError(IdentityError):
    """Raised when the face provider detects zero faces in the input image."""


class MultipleFacesDetectedError(IdentityError):
    """Raised when the face provider detects more than one face in the input image."""
