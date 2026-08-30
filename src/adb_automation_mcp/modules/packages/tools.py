"""Module-level, statically-introspectable tool functions for the packages module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.packages.service import (
    InstallExistingResult,
    InstallResult,
    PackageFilter,
    PackageList,
    PackagesService,
    UninstallResult,
)
from adb_automation_mcp.registry import category


@category("read")
async def list_packages(
    ctx: Context,
    serial: str,
    user_id: int | None = None,
    package_filter: PackageFilter | None = None,
) -> PackageList:
    """List installed Android packages on a device: `adb shell pm list packages`.

    Returns parsed package names only, not pm's raw text output.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        user_id: Restrict the listing to one Android user's package view
            (`--user ID`, see list_users). Omit to use pm's default user.
        package_filter: Restrict to "system" packages (`-s`) or
            "third_party" packages (`-3`) — pm's own mutually exclusive
            filter flags. Omit to list every package regardless of origin.

    Returns:
        The serial and every matching package name. An empty list is a
        normal result (e.g. no third-party apps installed), not an error.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error.

    Example:
        Called with serial="emulator-5554", package_filter="third_party". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "2 packages on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "packages": ["com.example.app", "com.example.other"]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    packages = cast(PackagesService, services["packages"])
    return await packages.list_packages(serial, user_id=user_id, package_filter=package_filter)


@category("write")
async def install_apk(
    ctx: Context,
    serial: str,
    apk_path: str,
    user_id: int | None = None,
    replace_existing: bool = False,
    allow_downgrade: bool = False,
    grant_runtime_permissions: bool = False,
    allow_test_packages: bool = False,
    force_sdk: bool = False,
) -> InstallResult:
    """Install an APK on a connected device (`adb install`).

    Exposes semantic installation options rather than raw adb/pm flags.
    Android's Package Manager remains the final authority on whether a
    requested installation is legal — these options select supported
    installation behavior, they never bypass signature checks, Package
    Manager restrictions, or (absent the matching option) SDK/downgrade
    restrictions.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        apk_path: Path to the APK to install, resolved by adb itself (a
            host path when running against a real device/emulator). Must
            not be empty.
        user_id: Install the APK for one Android user (`--user ID`, see
            list_users) instead of adb's default target.
        replace_existing: Replace/reinstall an already-installed version of
            this package (`-r`) instead of failing when one is present.
        allow_downgrade: Allow installing a lower versionCode than what's
            currently installed (`-d`), where Android's Package Manager
            permits it (documented as debuggable-package behavior — this
            does not override a build's own downgrade restrictions).
        grant_runtime_permissions: Grant all of the app's declared runtime
            permissions automatically at install time (`-g`).
        allow_test_packages: Allow installing an APK built with
            `android:testOnly="true"` (`-t`), which a plain install rejects.
        force_sdk: Ask the Package Manager to override its usual
            minSdkVersion/targetSdkVersion compatibility check
            (`--force-sdk`). Android still enforces every other install
            check normally.

    Returns:
        Whether the install succeeded, the requested apk_path and user_id,
        and which semantic options were requested (not raw flags).

    Error handling:
        Raises DeviceNotFoundError if serial doesn't match a connected
        device. Raises AndroidRejectionError when adb install reports a
        "Failure [REASON]" outcome — e.g. a signature mismatch, a
        downgrade/SDK/test-package restriction the requested options
        didn't cover, or insufficient storage — REASON is included in the
        error details. Raises InvalidArgumentError for an empty apk_path or
        a negative user_id. Any other non-zero exit surfaces as
        BackendError.

    Example:
        Called with serial="emulator-5554",
        apk_path="/tmp/app-debug.apk", replace_existing=True. A typical
        response:

        ```json
        {
          "status": "success",
          "message": "Installed /tmp/app-debug.apk on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "apk_path": "/tmp/app-debug.apk",
            "user_id": null,
            "replace_existing": true,
            "allow_downgrade": false,
            "grant_runtime_permissions": false,
            "allow_test_packages": false,
            "force_sdk": false,
            "success": true,
            "output": "Performing Streamed Install\\nSuccess\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    packages = cast(PackagesService, services["packages"])
    return await packages.install_apk(
        serial,
        apk_path,
        user_id=user_id,
        replace_existing=replace_existing,
        allow_downgrade=allow_downgrade,
        grant_runtime_permissions=grant_runtime_permissions,
        allow_test_packages=allow_test_packages,
        force_sdk=force_sdk,
    )


@category("destructive")
async def uninstall_package(
    ctx: Context,
    serial: str,
    package_name: str,
    user_id: int | None = None,
    keep_data: bool = False,
    version_code: int | None = None,
) -> UninstallResult:
    """Uninstall a package on a connected device (`adb shell pm uninstall`).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package to uninstall. Must not be empty.
        user_id: Uninstall the package for one Android user (`--user ID`,
            see list_users) rather than the device's normal (unscoped)
            uninstall behavior. Removing it for one user never removes it
            for every user — omit user_id for that instead.
        keep_data: Request that Android preserve the package's data/cache
            (`-k`) rather than wiping it. This is what pm's `-k` provides,
            not a stronger guarantee beyond what Package Manager itself
            does.
        version_code: Only uninstall if the installed package's version
            code matches (`--versionCode CODE`). Omit to uninstall
            regardless of version.

    Returns:
        The package name, target user (if any), whether data retention was
        requested, and whether the uninstall succeeded.

    Error handling:
        Raises DeviceNotFoundError if serial doesn't match a connected
        device. Raises PackageNotFoundError when the package isn't
        installed at all, or isn't installed for the targeted user.
        Raises UserNotFoundError when user_id doesn't correspond to an
        Android user on the device. Raises AndroidRejectionError for any
        other on-device Package Manager rejection (e.g. a version_code
        that doesn't match the installed package). Raises
        InvalidArgumentError for an empty package_name, a negative
        user_id, or a non-positive version_code. Any other non-zero exit
        surfaces as BackendError.

    Example:
        Called with serial="emulator-5554",
        package_name="com.example.app", user_id=10. A typical response:

        ```json
        {
          "status": "success",
          "message": "Uninstalled com.example.app on emulator-5554 for user 10.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "user_id": 10,
            "keep_data": false,
            "version_code": null,
            "success": true,
            "output": "Success\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    packages = cast(PackagesService, services["packages"])
    return await packages.uninstall_package(
        serial, package_name, user_id=user_id, keep_data=keep_data, version_code=version_code
    )


@category("write")
async def install_existing_for_user(
    ctx: Context, serial: str, package_name: str, user_id: int
) -> InstallExistingResult:
    """Make an already-installed package available to another Android user
    (`adb shell pm install-existing --user USER_ID PACKAGE`).

    This is distinct from install_apk: it never touches an APK file, it
    only extends an app that's already present on the device to another
    user's view of it (e.g. a work profile or a secondary user on a
    multi-user/automotive build).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The already-installed package to make available.
            Must not be empty.
        user_id: The Android user to make the package available to (see
            list_users).

    Returns:
        The package name, target user, and whether the operation
        succeeded. Requesting this for a user the package is already
        available to is not an error — pm install-existing is idempotent.

    Error handling:
        Raises DeviceNotFoundError if serial doesn't match a connected
        device. Raises PackageNotFoundError when package_name isn't
        installed on the device at all. Raises AndroidRejectionError for
        any other on-device Package Manager rejection. Raises
        InvalidArgumentError for an empty package_name or a negative
        user_id. Any other non-zero exit surfaces as BackendError.

        Note: `pm install-existing` does NOT validate the target user —
        verified live that a non-existent user_id (e.g. 42 on a
        single-user device) still returns "Package <name> installed for
        user: 42" and exit 0. This tool reports that as success; it cannot
        surface a bogus user_id as an error because pm itself doesn't.
        Use list_users first if the id must be known-good.

    Example:
        Called with serial="emulator-5554",
        package_name="com.example.app", user_id=10. A typical response:

        ```json
        {
          "status": "success",
          "message": "Made com.example.app available for user 10 on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "user_id": 10,
            "success": true,
            "output": "Package com.example.app installed for user: 10\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    packages = cast(PackagesService, services["packages"])
    return await packages.install_existing_for_user(serial, package_name, user_id)
