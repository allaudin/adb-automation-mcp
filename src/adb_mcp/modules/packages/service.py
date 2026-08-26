"""Domain logic for the packages module: installed-app management (install,
uninstall, clearing app cache/data, querying package status). Only
list_packages is implemented so far (`adb shell pm list packages`);
install/uninstall are deliberately out of scope for now.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import BackendError, DeviceNotFoundError

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


def _parse_package_list(output: str) -> list[str]:
    packages = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            packages.append(line[len("package:") :])
    return packages
