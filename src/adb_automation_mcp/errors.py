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


class RemoteFileNotFoundError(AdbError):
    """The device is reachable, but the requested remote path doesn't exist
    on it (e.g. `adb pull`'s "remote object '...' does not exist").
    """

    code = "REMOTE_FILE_NOT_FOUND"


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


class ComponentNotFoundError(AdbError):
    """An explicit component (`-n package/class`) passed to a command like
    `am broadcast` was malformed or unresolvable — `am` rejected it before
    the operation was attempted.
    """

    code = "COMPONENT_NOT_FOUND"


class PermissionDeniedError(AdbError):
    """The device rejected an operation with a "Permission Denial"
    SecurityException (e.g. `am broadcast` targeting a protected action the
    caller isn't allowed to send).
    """

    code = "PERMISSION_DENIED"


class BackgroundServiceRestrictedError(AdbError):
    """ActivityManager refused to start a service because the caller isn't
    allowed to start background services right now (Android 8+'s background
    execution limits — e.g. "Not allowed to start service ...: app is in
    background").
    """

    code = "BACKGROUND_SERVICE_RESTRICTED"


class PackageNotFoundError(AdbError):
    """The device is reachable, but no installed package matches the
    requested package_name (for the target user, when one was specified).
    """

    code = "PACKAGE_NOT_FOUND"


class CacheOnlyUnsupportedError(AdbError):
    """The connected device's `pm` doesn't recognize a cache-only-scoped
    operation (e.g. `pm clear --cache-only`'s `--cache-only` flag isn't
    supported on this Android version). Callers must not silently fall back
    to the unscoped/full-data equivalent — that has different, more
    destructive semantics.
    """

    code = "CACHE_ONLY_UNSUPPORTED"


class AndroidRejectionError(AdbError):
    """The device processed the request and explicitly declined it (e.g.
    `pm clear`'s bare "Failed" outcome) — a real, on-device rejection, not
    an adb/transport-level failure and not a bad request.
    """

    code = "ANDROID_REJECTED"


class PropertyWriteRejectedError(AdbError):
    """`setprop` reached the device but the property-service/SELinux rejected
    the write (e.g. a read-only property that's already been set) — distinct
    from PolicyViolationError, which blocks a call before it ever reaches the
    device.
    """

    code = "PROPERTY_WRITE_REJECTED"


class UiAutomatorFailedError(AdbError):
    """`uiautomator dump` itself failed to run (e.g. the uiautomator binary
    is missing on this build, or the command otherwise exited non-zero for a
    uiautomator-specific reason) — a tool/environment failure, distinct from
    UiHierarchyUnavailableError, where the command ran but found nothing to
    capture.
    """

    code = "UIAUTOMATOR_FAILED"


class UiHierarchyUnavailableError(AdbError):
    """`uiautomator dump` ran but could not obtain a root accessibility node
    for the device's current UI state (its well-known "ERROR: null root
    node returned by UiTestAutomationBridge." failure) — typically because
    the screen is off, locked, or otherwise has no inspectable window
    content right now.
    """

    code = "UI_HIERARCHY_UNAVAILABLE"


class PermissionNotDeclaredError(AdbError):
    """`pm grant` targeted a permission the package doesn't request/declare
    in its manifest (or, less commonly, a permission name unknown to the
    platform at all) — the grant was never attempted because there's
    nothing on the package to grant it against.
    """

    code = "PERMISSION_NOT_DECLARED"


class NonRuntimePermissionError(AdbError):
    """`pm grant` targeted a permission that isn't a runtime (dangerous)
    permission — normal/signature/install-time permissions aren't
    dynamically grantable this way; the platform rejects them as "not a
    changeable permission type".
    """

    code = "NON_RUNTIME_PERMISSION"


class PermissionPolicyRestrictedError(AdbError):
    """`pm grant` was rejected because the permission's state on this
    package is fixed by device/enterprise policy (e.g. a DevicePolicyManager
    restriction) — the grant can't be changed this way regardless of
    caller privilege.
    """

    code = "PERMISSION_POLICY_RESTRICTED"


class PowerStateUnavailableError(AdbError):
    """`dumpsys power` ran but its output didn't contain a recognizable
    `mWakefulness=...` line — the one field this tool treats as required
    couldn't be found, e.g. because dumpsys's internal format changed, the
    power service isn't registered, or the output was otherwise
    unrecognizable.
    """

    code = "POWER_STATE_UNAVAILABLE"


class MemoryInfoUnavailableError(AdbError):
    """`dumpsys meminfo` / `dumpsys procstats` ran but its output carried
    none of the markers the requesting tool reads — the dump's format
    drifted across Android versions, or the output was truncated /
    unrecognizable, so no structured snapshot could be built. Distinct from
    PACKAGE_NOT_RUNNING (the process simply isn't running) and from an empty
    but valid history result.
    """

    code = "MEMORY_INFO_UNAVAILABLE"


class ProcessMemoryUnavailableError(AdbError):
    """`dumpsys meminfo` ran and the target process exists, but the output
    carried none of the markers this tool reads (no "MEMINFO in pid" header
    and no "TOTAL PSS" / "App Summary" section) — meminfo's format drifted
    across Android versions, or the output was truncated/unrecognizable, so
    no snapshot could be built. Distinct from PACKAGE_NOT_RUNNING, where the
    process simply isn't running.
    """

    code = "PROCESS_MEMORY_UNAVAILABLE"


class NetworkToolUnavailableError(AdbError):
    """The `ip` command used to enumerate network interfaces isn't
    available on this device (e.g. "ip: not found") — a tool/environment
    limitation, not a connectivity failure.
    """

    code = "NETWORK_TOOL_UNAVAILABLE"


class ConnectivityStateUnavailableError(AdbError):
    """`dumpsys connectivity` ran but its output carried none of the markers
    this tool reads (neither an `Active default network:` line nor a
    `NetworkAgentInfo{...}` / `Current Networks:` section) — the dump's format
    drifted, the connectivity service isn't registered, or the output was
    truncated/unrecognizable, so no snapshot could be built.
    """

    code = "CONNECTIVITY_STATE_UNAVAILABLE"


class ContentProviderNotFoundError(AdbError):
    """`adb shell content query` reached the device but no ContentProvider is
    exported/registered for the requested authority (its "Could not find
    provider: <authority>" / "Error while accessing provider" failure). The
    `content` command reports this on stdout and still exits 0, so it's
    surfaced here rather than swallowed as an empty result.
    """

    code = "CONTENT_PROVIDER_NOT_FOUND"


class InstrumentationFailedError(AdbError):
    """`adb shell am instrument` could not start the instrumentation at all
    (its "INSTRUMENTATION_FAILED: <component>" / "Unable to find
    instrumentation info" outcome) — the test package or runner class isn't
    installed, or the component is malformed. `am` reports this on stdout and
    still exits 0. Distinct from a run that started and then had test
    failures, which is returned as data.
    """

    code = "INSTRUMENTATION_FAILED"


class PortForwardConflictError(AdbError):
    """`adb forward --no-rebind` was asked to bind a host endpoint that already
    has a forward on it ("cannot rebind existing socket"). The caller explicitly
    opted out of silently replacing the existing mapping, so this is surfaced
    rather than swallowed — remove the existing forward first, or retry without
    no_rebind to take it over.
    """

    code = "PORT_FORWARD_CONFLICT"


class DisplayInfoUnavailableError(AdbError):
    """`dumpsys display` ran but its output contained no recognizable display
    records (neither a parseable `mViewports=[...]` line nor a `Display
    States:` section) — every Android device has at least one display, so
    zero parsed displays means the dump's format drifted or the output was
    truncated/unrecognizable, not that there genuinely are none.
    """

    code = "DISPLAY_INFO_UNAVAILABLE"


class DeviceClockUnavailableError(AdbError):
    """`date` ran but its output didn't match the machine-readable
    timestamp format this tool requests — e.g. because the device's `date`
    binary doesn't support the requested `+FORMAT` directives, or returned
    unexpected/empty output.
    """

    code = "DEVICE_CLOCK_UNAVAILABLE"
