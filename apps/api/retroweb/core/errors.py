"""Application errors mapped to HTTP responses with machine-readable codes.

The frontend switches on ``code`` to show specific messages
("This game's ROM file is missing") instead of a generic failure.
"""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        if code:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    """The requested resource does not exist."""

    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    """The request was malformed."""

    status_code = 422
    code = "validation_error"


class RomMissingError(AppError):
    """The ROM file for this game is missing from storage."""

    status_code = 404
    code = "rom_missing"


class UnsupportedRomError(AppError):
    """The file is not a supported ROM for this system."""

    status_code = 422
    code = "unsupported_rom"


class InvalidFilenameError(AppError):
    """The file name is not acceptable."""

    status_code = 422
    code = "invalid_filename"


class FileTooLargeError(AppError):
    """The uploaded file exceeds the size limit."""

    status_code = 413
    code = "file_too_large"


class DuplicateRomError(AppError):
    """A file with the same hash is already in the library."""

    status_code = 409
    code = "duplicate_rom"


class SessionStateError(AppError):
    """The play session is not in a state that allows this action."""

    status_code = 409
    code = "session_already_ended"


class StorageError(AppError):
    """The storage backend failed."""

    status_code = 500
    code = "storage_error"
