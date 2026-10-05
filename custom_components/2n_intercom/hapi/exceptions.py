"""Exceptions for the 2N HTTP API client."""

from __future__ import annotations


class TwoNError(Exception):
    """Base exception for all 2N API errors."""


class TwoNConnectionError(TwoNError):
    """Raised when the device cannot be reached."""


class TwoNAuthError(TwoNError):
    """Raised when authentication fails (bad credentials)."""


class TwoNPrivilegeError(TwoNAuthError):
    """Raised when the account lacks the privilege for an endpoint."""


class TwoNApiError(TwoNError):
    """Raised when the device returns an API error envelope."""

    def __init__(
        self,
        code: int,
        description: str = "",
        param: str | None = None,
    ) -> None:
        """Initialize with the device's error code, description and parameter."""
        self.code = code
        self.description = description
        self.param = param
        message = f"API error {code}: {description}"
        if param:
            message += f" (param: {param})"
        super().__init__(message)


class TwoNNotSupportedError(TwoNApiError):
    """Raised when a function is not supported or disabled on the device."""
