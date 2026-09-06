"""Domain logic for the packages module: installed-app management on a
connected device — listing (`adb shell pm list packages`), installing
(`adb install`), uninstalling (`adb shell pm uninstall`), making an
already-installed package available to another Android user
(`adb shell pm install-existing`), and resolving a package's on-device APK
paths (`adb shell pm path`, split APKs included). Clearing app cache/data
lives in a separate module (app_data); APK bundles, APEX, staged
installs/sessions, install-location management, and enable/disable/suspend
are all deliberately out of scope for now.
"""

from __future__ import annotations

import re
import shlex
from typing import Literal

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    AndroidRejectionError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PackageNotFoundError,
    UserNotFoundError,
)

PackageFilter = Literal["system", "third_party"]


class PackageList(BaseModel):
    """Installed package names, as reported by `adb shell pm list packages`.

    Deliberately minimal: just package names, not pm list packages' other
    per-entry detail (`-f` associated APK path, `-i` installer, `-u` include
    uninstalled) — those are out of scope for this initial result shape. An
    empty list is a normal, valid result (e.g. an unused package_filter/user
    combination on a minimal device), not an error.
    """

    serial: str
    packages: list[str]

    def summary(self) -> str:
        n = len(self.packages)
        plural = "" if n == 1 else "s"
        return f"{n} package{plural} on {self.serial}."


class InstallResult(BaseModel):
    """Outcome of installing an APK (`adb install`).

    Not verified live (no device was available in this environment) —
    shaped on `adb install`'s documented, long-stable output ("Performing
    Streamed Install" followed by either a bare "Success" or a
    "Failure [REASON]" line) — see PackagesService.install_apk's Error
    handling for how a Failure reason is classified and raised instead of
    returned as data. success is always True here; it's kept as an explicit
    field since a caller inspecting just the data payload should still see
    it stated, not merely implied by the envelope's status. The five bool
    fields echo back exactly which semantic options were requested (not
    which raw pm/adb flags were sent — this project doesn't expose those),
    so a caller can see what materially affected the installation without
    re-deriving it from the call arguments.
    """

    serial: str
    apk_path: str
    user_id: int | None
    replace_existing: bool
    allow_downgrade: bool
    grant_runtime_permissions: bool
    allow_test_packages: bool
    force_sdk: bool
    success: bool
    output: str

    def summary(self) -> str:
        target = f" for user {self.user_id}" if self.user_id is not None else ""
        return f"Installed {self.apk_path} on {self.serial}{target}."


class UninstallResult(BaseModel):
    """Outcome of uninstalling a package (`adb shell pm uninstall`).

    Not verified live (no device was available in this environment) —
    shaped on `PackageManagerShellCommand.runUninstall()`'s documented
    behavior: a bare "Success" on success, a "Failure [REASON]" line when
    Android declines the request (e.g. the package isn't installed, or
    isn't installed for the targeted user), on a non-zero exit — see
    PackagesService.uninstall_package's Error handling for how each is
    classified and raised instead of returned as data. success is always
    True here; it's kept as an explicit field for the same reason as
    InstallResult.success. user_id is None only when the call targeted the
    device's normal (unscoped) uninstall behavior — a user_id-scoped call
    never silently falls back to removing the package for every user.
    """

    serial: str
    package_name: str
    user_id: int | None
    keep_data: bool
    version_code: int | None
    success: bool
    output: str

    def summary(self) -> str:
        scope = f" for user {self.user_id}" if self.user_id is not None else ""
        return f"Uninstalled {self.package_name} on {self.serial}{scope}."


class InstallExistingResult(BaseModel):
    """Outcome of making an already-installed package available to another
    Android user (`adb shell pm install-existing`).

    Not verified live (no device was available in this environment) —
    shaped on `PackageManagerShellCommand.runInstallExisting()`'s
    documented "Package NAME installed for user: ID" success wording,
    which is idempotent (installing for a user the package is already
    available to still reports the same success line rather than erroring)
    — see PackagesService.install_existing_for_user's Error handling for
    how genuine failures are classified. success is always True here for
    the same reason as InstallResult.success.
    """

    serial: str
    package_name: str
    user_id: int
    success: bool
    output: str

    def summary(self) -> str:
        return f"Made {self.package_name} available for user {self.user_id} on {self.serial}."


class PackagePathInfo(BaseModel):
    """On-device APK paths for one installed package, from `adb shell pm path`.

    `pm path` prints one "package:<path>" line per APK. A monolithically
    installed app has a single path; a split-installed app has a base plus one
    or more `split_config.*` APKs. paths is the authoritative list in pm's own
    order; base_apk / split_apks are a best-effort split-out (base identified by
    a trailing "/base.apk", else the first path, since pm lists the base first).
    """

    serial: str
    package_name: str
    user_id: int | None
    paths: list[str]
    base_apk: str | None
    split_apks: list[str]

    def summary(self) -> str:
        scope = f" (user {self.user_id})" if self.user_id is not None else ""
        n = len(self.paths)
        if n == 1:
            return f"{self.package_name} on {self.serial}{scope}: 1 APK."
        return f"{self.package_name} on {self.serial}{scope}: {n} APKs (base + {len(self.split_apks)} split)."


_ENABLED_STATE_NAMES = {
    "0": "default",
    "1": "enabled",
    "2": "disabled",
    "3": "disabled_by_user",
    "4": "disabled_until_used",
}


class PackageUserInfo(BaseModel):
    """Per-Android-user state for a package, from a `dumpsys package` "User N:"
    install-state line. Any field pm's output for this build doesn't carry is
    left null rather than guessed.
    """

    user_id: int
    installed: bool | None
    enabled_state: str
    stopped: bool | None
    hidden: bool | None
    suspended: bool | None


class PackageInfo(BaseModel):
    """A curated, deliberately minimal snapshot of one installed package, parsed
    from `adb shell dumpsys package <pkg>`. This is NOT the whole dumpsys dump —
    just the stable fields worth an automation contract. Every field is
    best-effort: a value pm's output for this Android version doesn't carry
    comes back null (or an empty list), never an error.
    """

    serial: str
    package_name: str
    uid: int | None
    version_code: int | None
    version_name: str | None
    min_sdk: int | None
    target_sdk: int | None
    code_path: str | None
    data_dir: str | None
    installer_package_name: str | None
    first_install_time: str | None
    last_update_time: str | None
    is_system: bool
    flags: list[str]
    users: list[PackageUserInfo]
    requested_permissions: list[str]
    granted_permissions: list[str]

    def summary(self) -> str:
        ver = self.version_name or (str(self.version_code) if self.version_code is not None else "?")
        kind = "system" if self.is_system else "user"
        return (
            f"{self.package_name} {ver} ({kind}) on {self.serial}: "
            f"{len(self.granted_permissions)} granted / "
            f"{len(self.requested_permissions)} requested permissions, "
            f"{len(self.users)} user(s)."
        )


class PackagesService:
    """Installed-app management logic."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    @staticmethod
    def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
        if result.exit_code == 0:
            return
        # Same "adb: device '<serial>' not found" convention verified live
        # for other modules' shell commands (e.g. user's) — the adb-client
        # rejects an unknown serial before any command reaches a device.
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        if "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})

    async def list_packages(
        self,
        serial: str,
        user_id: int | None = None,
        package_filter: PackageFilter | None = None,
    ) -> PackageList:
        parts = ["pm", "list", "packages"]
        if package_filter == "system":
            parts.append("-s")
        elif package_filter == "third_party":
            parts.append("-3")
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        result = await self._backend.shell(serial, " ".join(parts))
        self._raise_for_shell_failure(serial, result)
        return PackageList(serial=serial, packages=_parse_package_list(result.stdout))

    async def install_apk(
        self,
        serial: str,
        apk_path: str,
        user_id: int | None = None,
        replace_existing: bool = False,
        allow_downgrade: bool = False,
        grant_runtime_permissions: bool = False,
        allow_test_packages: bool = False,
        force_sdk: bool = False,
    ) -> InstallResult:
        if not apk_path.strip():
            raise InvalidArgumentError("apk_path must not be empty.", details={"serial": serial})
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.", details={"serial": serial, "user_id": user_id}
            )

        # Semantic options map to adb install's own supported flags — Android
        # itself still enforces signature checks, Package Manager
        # restrictions, and (absent allow_downgrade/force_sdk) downgrade/SDK
        # restrictions; none of these flags bypass that.
        flags: list[str] = []
        if user_id is not None:
            flags.extend(["--user", str(user_id)])
        if replace_existing:
            flags.append("-r")
        if allow_downgrade:
            flags.append("-d")
        if grant_runtime_permissions:
            flags.append("-g")
        if allow_test_packages:
            flags.append("-t")
        if force_sdk:
            flags.append("--force-sdk")

        result = await self._backend.install(serial, apk_path, flags)
        _raise_for_install_failure(serial, apk_path, result)
        return InstallResult(
            serial=serial,
            apk_path=apk_path,
            user_id=user_id,
            replace_existing=replace_existing,
            allow_downgrade=allow_downgrade,
            grant_runtime_permissions=grant_runtime_permissions,
            allow_test_packages=allow_test_packages,
            force_sdk=force_sdk,
            success=True,
            output=result.stdout,
        )

    async def uninstall_package(
        self,
        serial: str,
        package_name: str,
        user_id: int | None = None,
        keep_data: bool = False,
        version_code: int | None = None,
    ) -> UninstallResult:
        if not package_name.strip():
            raise InvalidArgumentError("package_name must not be empty.", details={"serial": serial})
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.", details={"serial": serial, "user_id": user_id}
            )
        if version_code is not None and version_code < 1:
            raise InvalidArgumentError(
                "version_code must be a positive integer.",
                details={"serial": serial, "version_code": version_code},
            )

        # Routed through `pm uninstall` via shell rather than the backend's
        # dedicated install/uninstall primitive, whose (serial, package,
        # keep_data) signature has no way to express --user or
        # --versionCode. Reusing shell() here follows the same convention
        # list_packages/grant_permission/clear_app_data already use for pm
        # subcommands, and keeps AdbBackend unchanged rather than growing a
        # new primitive for every pm flag.
        parts = ["pm", "uninstall"]
        if keep_data:
            parts.append("-k")
        if user_id is not None:
            # --user scopes the uninstall to one Android user; omitting it
            # uses pm's normal (unscoped) uninstall behavior. Never widen a
            # user-scoped request into an all-users uninstall.
            parts.extend(["--user", str(user_id)])
        if version_code is not None:
            parts.extend(["--versionCode", str(version_code)])
        parts.append(shlex.quote(package_name))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_uninstall_failure(serial, package_name, user_id, version_code, result)
        return UninstallResult(
            serial=serial,
            package_name=package_name,
            user_id=user_id,
            keep_data=keep_data,
            version_code=version_code,
            success=True,
            output=result.stdout,
        )

    async def install_existing_for_user(
        self, serial: str, package_name: str, user_id: int
    ) -> InstallExistingResult:
        if not package_name.strip():
            raise InvalidArgumentError("package_name must not be empty.", details={"serial": serial})
        if user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.", details={"serial": serial, "user_id": user_id}
            )

        command = f"pm install-existing --user {user_id} {shlex.quote(package_name)}"
        result = await self._backend.shell(serial, command)
        _raise_for_install_existing_failure(serial, package_name, user_id, result)
        return InstallExistingResult(
            serial=serial, package_name=package_name, user_id=user_id, success=True, output=result.stdout
        )

    async def get_package_path(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> PackagePathInfo:
        if not package_name.strip():
            raise InvalidArgumentError("package_name must not be empty.", details={"serial": serial})
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.",
                details={"serial": serial, "user_id": user_id},
            )

        parts = ["pm", "path"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))
        result = await self._backend.shell(serial, " ".join(parts))

        paths = _parse_pm_path(result.stdout)
        if not paths:
            # `pm path` gives no positive output for a package it can't resolve.
            # On some builds it prints "Unknown package" / "Error: ... not
            # found"; on others (e.g. the AOSP automotive image this was
            # verified against) it just exits 1 with nothing at all. An
            # unavailable --user scope produces the same empty result, so the
            # message names both possibilities.
            _raise_for_pm_path_failure(serial, package_name, user_id, result)
            scope = f" for user {user_id}" if user_id is not None else ""
            raise PackageNotFoundError(
                f"pm path returned no APK path for {package_name}{scope} — the "
                "package is not installed" + (", or not for that user." if user_id is not None else "."),
                details={"serial": serial, "package_name": package_name, "user_id": user_id},
            )

        base_apk = next(
            (p for p in paths if p.rsplit("/", 1)[-1] == "base.apk"), paths[0]
        )
        return PackagePathInfo(
            serial=serial,
            package_name=package_name,
            user_id=user_id,
            paths=paths,
            base_apk=base_apk,
            split_apks=[p for p in paths if p != base_apk],
        )

    async def get_package_info(self, serial: str, package_name: str) -> PackageInfo:
        if not package_name.strip():
            raise InvalidArgumentError("package_name must not be empty.", details={"serial": serial})

        result = await self._backend.shell(serial, f"dumpsys package {shlex.quote(package_name)}")
        self._raise_for_shell_failure(serial, result)

        text = result.stdout
        # dumpsys exits 0 even for an unknown package; it says so in words, and
        # never emits a "Package [<name>]" block for one.
        if f"Unable to find package: {package_name}" in text or f"Package [{package_name}]" not in text:
            raise PackageNotFoundError(
                f"dumpsys package has no record of {package_name} on {serial}.",
                details={"serial": serial, "package_name": package_name},
            )

        return _parse_dumpsys_package(serial, package_name, text)


def _parse_pm_path(output: str) -> list[str]:
    paths: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            candidate = line[len("package:") :].strip()
            if candidate:
                paths.append(candidate)
    return paths


def _raise_for_pm_path_failure(
    serial: str, package_name: str, user_id: int | None, result: CommandResult
) -> None:
    message = (result.stderr or result.stdout).strip()
    if _is_device_not_found(message):
        raise DeviceNotFoundError(message, details={"serial": serial})
    combined = f"{result.stdout}\n{result.stderr}"
    if _MISSING_USER_RE.search(combined) is not None:
        raise UserNotFoundError(
            message or f"no such user {user_id}",
            details={"serial": serial, "package_name": package_name, "user_id": user_id},
        )
    if "Unknown package" in combined or "not found" in combined:
        raise PackageNotFoundError(
            message or f"pm path could not find {package_name}",
            details={"serial": serial, "package_name": package_name, "user_id": user_id},
        )
    # An explicit non-zero exit with some other wording is a real backend
    # failure; a zero exit with empty output falls through to the caller's
    # PackageNotFoundError.
    if result.exit_code != 0 and message:
        raise BackendError(
            message,
            details={
                "serial": serial,
                "package_name": package_name,
                "user_id": user_id,
                "exit_code": result.exit_code,
            },
        )


_PKG_BLOCK_RE = re.compile(r"^  Package \[(?P<name>[^\]]+)\] \(")
_KV_RE = re.compile(r"(\w+)=((?:\[[^\]]*\])|(?:\S+))")
_GRANTED_TRUE_RE = re.compile(r"^\s+(?P<perm>[\w.]+): granted=true\b")
_USER_LINE_RE = re.compile(r"^\s+User (?P<uid>\d+):\s")


def _first_value(block: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for raw in block:
        stripped = raw.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return value or None
    return None


def _parse_flags(block: list[str], key: str) -> list[str]:
    for raw in block:
        stripped = raw.strip()
        if stripped.startswith(f"{key}=["):
            inner = stripped[stripped.index("[") + 1 : stripped.rindex("]")] if "]" in stripped else ""
            return inner.split()
    return []


def _parse_requested_permissions(block: list[str]) -> list[str]:
    perms: list[str] = []
    collecting = False
    for raw in block:
        stripped = raw.strip()
        if stripped == "requested permissions:":
            collecting = True
            continue
        if collecting:
            # The list ends at the next "<something>:" section header or a
            # non-permission-looking line.
            if not stripped or stripped.endswith(":") or "=" in stripped:
                break
            perms.append(stripped)
    return perms


def _tri_bool(kv: dict[str, str], name: str) -> bool | None:
    v = kv.get(name)
    return None if v is None else v == "true"


def _parse_user_states(block: list[str]) -> list[PackageUserInfo]:
    users: list[PackageUserInfo] = []
    for raw in block:
        m = _USER_LINE_RE.match(raw)
        if m is None or "installed=" not in raw:
            continue
        kv = dict(_KV_RE.findall(raw))
        users.append(
            PackageUserInfo(
                user_id=int(m.group("uid")),
                installed=_tri_bool(kv, "installed"),
                enabled_state=_ENABLED_STATE_NAMES.get(kv.get("enabled", ""), "unknown"),
                stopped=_tri_bool(kv, "stopped"),
                hidden=_tri_bool(kv, "hidden"),
                suspended=_tri_bool(kv, "suspended"),
            )
        )
    return users


def _parse_granted_permissions(full_text: str) -> list[str]:
    # Scanned over the whole dumpsys output, not just the Package block: for a
    # shared-uid package the runtime-permission grants live in a later
    # "Shared users:" section. dumpsys package <pkg> is filtered to the one
    # package, so every "granted=true" line here belongs to it.
    seen: dict[str, None] = {}
    for line in full_text.splitlines():
        m = _GRANTED_TRUE_RE.match(line)
        if m is not None:
            seen.setdefault(m.group("perm"), None)
    return list(seen)


def _parse_dumpsys_package(serial: str, package_name: str, text: str) -> PackageInfo:
    lines = text.splitlines()
    start: int | None = None
    for i, ln in enumerate(lines):
        m = _PKG_BLOCK_RE.match(ln)
        if m is not None and m.group("name") == package_name:
            start = i
            break
    if start is None:
        # The caller already checked for the block; treat a mismatch here as a
        # malformed dump rather than crashing.
        return PackageInfo(
            serial=serial,
            package_name=package_name,
            uid=None,
            version_code=None,
            version_name=None,
            min_sdk=None,
            target_sdk=None,
            code_path=None,
            data_dir=None,
            installer_package_name=None,
            first_install_time=None,
            last_update_time=None,
            is_system=False,
            flags=[],
            users=[],
            requested_permissions=[],
            granted_permissions=_parse_granted_permissions(text),
        )

    end = len(lines)
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln and not ln.startswith(" "):  # next column-0 section
            end = i
            break
        if _PKG_BLOCK_RE.match(ln):  # another package block
            end = i
            break
    block = lines[start:end]

    version_code: int | None = None
    min_sdk: int | None = None
    target_sdk: int | None = None
    version_line = _first_value(block, "versionCode")
    if version_line is not None:
        # "versionCode=4500 minSdk=24 targetSdk=34" — _first_value returns only
        # the first whitespace-delimited token, so re-scan the raw line for the
        # siblings.
        for raw in block:
            if raw.strip().startswith("versionCode="):
                kv = dict(_KV_RE.findall(raw))
                version_code = _safe_int(kv.get("versionCode"))
                min_sdk = _safe_int(kv.get("minSdk"))
                target_sdk = _safe_int(kv.get("targetSdk"))
                break

    installer = _first_value(block, "installerPackageName")
    if installer == "null":
        installer = None

    flags = _parse_flags(block, "flags") or _parse_flags(block, "pkgFlags")

    return PackageInfo(
        serial=serial,
        package_name=package_name,
        uid=_safe_int(_first_value(block, "appId") or _first_value(block, "userId")),
        version_code=version_code,
        version_name=_first_value(block, "versionName"),
        min_sdk=min_sdk,
        target_sdk=target_sdk,
        code_path=_first_value(block, "codePath"),
        data_dir=_first_value(block, "dataDir"),
        installer_package_name=installer,
        first_install_time=_first_value(block, "firstInstallTime"),
        last_update_time=_first_value(block, "lastUpdateTime"),
        is_system="SYSTEM" in flags,
        flags=flags,
        users=_parse_user_states(block),
        requested_permissions=_parse_requested_permissions(block),
        granted_permissions=_parse_granted_permissions(text),
    )


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_package_list(output: str) -> list[str]:
    packages = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            packages.append(line[len("package:") :])
    return packages


# adb install / pm uninstall / pm install-existing all report a rejection the
# same way: a "Failure [REASON]" line, where REASON is a PackageManager
# result-code name (install) or a short phrase (uninstall).
_FAILURE_REASON_RE = re.compile(r"Failure\s*\[(?P<reason>[^\]]*)\]")

# Multiple observed/documented phrasings for "no Android user with this ID
# exists on the device" across pm's install/uninstall/install-existing
# shell-command error paths — matched broadly since the exact wording isn't
# verified live (no device was available in this environment).
_MISSING_USER_RE = re.compile(
    r"(does not exist|has been removed|bad user number|no such user|unknown user)", re.IGNORECASE
)


def _is_device_not_found(message: str) -> bool:
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's, app_data's) — the adb-client rejects an
    # unknown serial before any command reaches a device.
    return message.startswith("adb:") and "not found" in message


def _raise_for_install_failure(serial: str, apk_path: str, result: CommandResult) -> None:
    message = (result.stderr or result.stdout).strip() or "adb install exited non-zero."
    if _is_device_not_found(message):
        raise DeviceNotFoundError(message, details={"serial": serial})

    combined = f"{result.stdout}\n{result.stderr}"
    match = _FAILURE_REASON_RE.search(combined)
    if match is not None:
        reason = match.group("reason").strip()
        # A genuine, on-device Package Manager decision (signature
        # mismatch, downgrade/SDK/test-package restriction not covered by
        # the requested options, insufficient storage, etc.) — not a
        # transport failure and not a bad request.
        raise AndroidRejectionError(
            f"pm install rejected the request: {reason}",
            details={"serial": serial, "apk_path": apk_path, "reason": reason},
        )

    if result.exit_code != 0:
        raise BackendError(
            message, details={"serial": serial, "apk_path": apk_path, "exit_code": result.exit_code}
        )


def _raise_for_uninstall_failure(
    serial: str,
    package_name: str,
    user_id: int | None,
    version_code: int | None,
    result: CommandResult,
) -> None:
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if _is_device_not_found(message):
        raise DeviceNotFoundError(message, details={"serial": serial})

    combined = f"{result.stdout}\n{result.stderr}"
    if _MISSING_USER_RE.search(combined) is not None:
        raise UserNotFoundError(
            message, details={"serial": serial, "package_name": package_name, "user_id": user_id}
        )

    match = _FAILURE_REASON_RE.search(combined)
    if match is not None:
        reason = match.group("reason").strip()
        internal_error = "DELETE_FAILED_INTERNAL_ERROR" in reason
        # A --versionCode that doesn't match the installed package can't be
        # satisfied: pm reports a bare "Failure [DELETE_FAILED_INTERNAL_ERROR]"
        # (verified live). The package IS installed, just not at that version,
        # so this is an on-device rejection, not "package not found".
        if internal_error and version_code is not None:
            raise AndroidRejectionError(
                f"pm uninstall could not satisfy --versionCode {version_code} for "
                f"{package_name}: {reason}",
                details={
                    "serial": serial,
                    "package_name": package_name,
                    "user_id": user_id,
                    "version_code": version_code,
                    "reason": reason,
                },
            )
        # pm uninstall reports both "package was never installed" and
        # "package isn't installed for the targeted user" as a Failure
        # whose reason names the scope ("not installed for <id>") or a
        # generic internal-error code — either way, nothing matched to
        # remove.
        if "not installed" in reason.lower() or internal_error:
            raise PackageNotFoundError(
                f"pm uninstall could not find {package_name}: {reason}",
                details={"serial": serial, "package_name": package_name, "user_id": user_id},
            )
        raise AndroidRejectionError(
            f"pm uninstall rejected the request: {reason}",
            details={"serial": serial, "package_name": package_name, "user_id": user_id, "reason": reason},
        )

    if result.exit_code != 0:
        raise BackendError(
            message,
            details={
                "serial": serial,
                "package_name": package_name,
                "user_id": user_id,
                "exit_code": result.exit_code,
            },
        )


def _raise_for_install_existing_failure(
    serial: str, package_name: str, user_id: int, result: CommandResult
) -> None:
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if _is_device_not_found(message):
        raise DeviceNotFoundError(message, details={"serial": serial})

    combined = f"{result.stdout}\n{result.stderr}"
    if _MISSING_USER_RE.search(combined) is not None:
        raise UserNotFoundError(
            message, details={"serial": serial, "package_name": package_name, "user_id": user_id}
        )
    # Same "Unknown package" wording used by app_data's `pm clear` and
    # permissions' `pm grant` handling — pm resolves the package before
    # anything else, across every pm subcommand that takes one.
    if "Unknown package" in combined:
        raise PackageNotFoundError(
            message, details={"serial": serial, "package_name": package_name, "user_id": user_id}
        )

    match = _FAILURE_REASON_RE.search(combined)
    if match is not None:
        reason = match.group("reason").strip()
        raise AndroidRejectionError(
            f"pm install-existing rejected the request: {reason}",
            details={"serial": serial, "package_name": package_name, "user_id": user_id, "reason": reason},
        )

    if result.exit_code != 0:
        raise BackendError(
            message,
            details={
                "serial": serial,
                "package_name": package_name,
                "user_id": user_id,
                "exit_code": result.exit_code,
            },
        )
