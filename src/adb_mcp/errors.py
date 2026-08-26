"""Typed exception hierarchy for every classifiable failure this server can raise.

Backend and service code never build a response envelope directly — they raise one of
these, and the registry's ``wrap_with_envelope`` converts it into a ``ToolResponse``
with the exception's ``code``, ``details``, ``retryable``, and ``remediation``.
"""

from __future__ import annotations

from typing import Any


class AdbError(Exception):
    """Base class for every classifiable failure in this server.

    Subclasses set ``code`` (and ``retryable`` where relevant) as class-level
    defaults; ``message``, ``details``, and ``remediation`` are supplied per raise
    site, since those are specific to the exact failure being reported.
    """

    code: str = "INTERNAL_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        self.remediation = remediation


class DeviceNotFoundError(AdbError):
    """No connected device matches the requested serial."""

    code = "DEVICE_NOT_FOUND"


class UserNotFoundError(AdbError):
    """The device is reachable, but no Android user with the requested ID
    exists on it.
    """

    code = "USER_NOT_FOUND"


class PackageNotRunningError(AdbError):
    """The device is reachable, but no running process was found for the
    requested package — `pidof` doesn't distinguish "not installed" from
    "installed but not currently running", so neither does this.
    """

    code = "PACKAGE_NOT_RUNNING"


class AmbiguousDeviceError(AdbError):
    """A serial was omitted but more than one device is connected."""

    code = "AMBIGUOUS_DEVICE"


class DeviceUnauthorizedError(AdbError):
    """The device is present but hasn't authorized USB debugging for this host."""

    code = "DEVICE_UNAUTHORIZED"


class DeviceOfflineError(AdbError):
    """The device is present but adb reports it as offline (often transient)."""

    code = "DEVICE_OFFLINE"
    retryable = True


class AdbTimeoutError(AdbError):
    """An adb command exceeded its configured timeout."""

    code = "TIMEOUT"
    retryable = True


class AdbUnavailableError(AdbError):
    """The adb binary or adb server itself is unreachable on this host."""

    code = "ADB_UNAVAILABLE"


class BackendError(AdbError):
    """adb exited non-zero for a reason not otherwise classified."""

    code = "BACKEND_ERROR"


class PolicyViolationError(AdbError):
    """A call-time policy check rejected this call (e.g. a host path outside the
    configured local_root for push_file/pull_file).
    """

    code = "POLICY_DENIED"


class LogSessionNotFoundError(AdbError):
    """No active log session matches the requested session_id — it was never
    started, or was already stopped.
    """

    code = "LOG_SESSION_NOT_FOUND"


class InvalidArgumentError(AdbError):
    """A caller-supplied argument combination is self-contradictory (e.g. two
    mutually exclusive optional parameters both set) — a bad call, not an adb
    or device failure.
    """

    code = "INVALID_ARGUMENT"
