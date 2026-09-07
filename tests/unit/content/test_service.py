"""Layer 1 unit tests: ContentService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import shlex

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    ContentProviderNotFoundError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.content.service import ContentService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.command: str | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.command = command
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_query_content__minimal_command_and_row_parse() -> None:
    backend = RecordingBackend()

    result = await ContentService(backend).query_content(
        "emulator-5554", "content://settings/system"
    )

    assert backend.command == "content query --uri content://settings/system"
    assert result.serial == "emulator-5554"
    assert result.uri == "content://settings/system"
    assert result.user_id is None
    assert result.row_count == 5
    assert result.rows[2] == {"_id": "0", "name": "volume_music", "value": "5"}
    # a value that itself contains "=" and "&" survives intact
    assert result.rows[3]["value"] == (
        "content://media/internal/audio/media/139?title=Girtab&canonical=1"
    )
    # literal NULL -> None
    assert result.rows[4]["value"] is None


@pytest.mark.asyncio
async def test_query_content__all_options_map_to_flags() -> None:
    backend = RecordingBackend()

    await ContentService(backend).query_content(
        "emulator-5554",
        "content://com.example/items",
        projection=["_id", "name"],
        where="name='x'",
        sort="name ASC",
        user_id=10,
    )

    assert backend.command is not None
    tokens = shlex.split(backend.command)
    assert tokens[:4] == ["content", "query", "--uri", "content://com.example/items"]
    assert tokens[tokens.index("--user") + 1] == "10"
    assert tokens[tokens.index("--projection") + 1] == "_id:name"
    assert tokens[tokens.index("--where") + 1] == "name='x'"
    assert tokens[tokens.index("--sort") + 1] == "name ASC"


@pytest.mark.asyncio
async def test_query_content__non_content_uri_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ContentService(ExplodingBackend()).query_content(
            "emulator-5554", "http://not-a-provider"
        )


@pytest.mark.asyncio
async def test_query_content__blank_projection_entry_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ContentService(ExplodingBackend()).query_content(
            "emulator-5554", "content://x/y", projection=["_id", "  "]
        )


@pytest.mark.asyncio
async def test_query_content__negative_user_id_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ContentService(ExplodingBackend()).query_content(
            "emulator-5554", "content://x/y", user_id=-1
        )


@pytest.mark.asyncio
async def test_query_content__no_result_is_valid_empty() -> None:
    backend = FakeBackend(content_query_result=_cr(stdout="No result found.\n"))

    result = await ContentService(backend).query_content("emulator-5554", "content://x/y")

    assert result.row_count == 0
    assert result.rows == []


@pytest.mark.asyncio
async def test_query_content__single_row() -> None:
    backend = FakeBackend(
        content_query_result=_cr(stdout="Row: 0 name=volume_music, value=5\n")
    )

    result = await ContentService(backend).query_content("emulator-5554", "content://x/y")

    assert result.row_count == 1
    assert result.rows == [{"name": "volume_music", "value": "5"}]


@pytest.mark.asyncio
async def test_query_content__missing_provider_raises_structured_error() -> None:
    backend = FakeBackend(
        content_query_result=_cr(
            stdout=(
                "Error while accessing provider:nonexistent.provider\n"
                "java.lang.IllegalStateException: Could not find provider: nonexistent.provider\n"
                "\tat com.android.commands.content.Content$Command.execute(Content.java:519)\n"
            )
        )
    )

    with pytest.raises(ContentProviderNotFoundError):
        await ContentService(backend).query_content(
            "emulator-5554", "content://nonexistent.provider/x"
        )


@pytest.mark.asyncio
async def test_query_content__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        content_query_result=_cr(
            stdout="java.lang.SecurityException: Permission Denial: opening provider ...\n"
        )
    )

    with pytest.raises(PermissionDeniedError):
        await ContentService(backend).query_content(
            "emulator-5554", "content://com.android.contacts/data"
        )


@pytest.mark.asyncio
async def test_query_content__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        content_query_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await ContentService(backend).query_content("bogus", "content://x/y")


@pytest.mark.asyncio
async def test_query_content__unclassified_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(content_query_result=_cr(stderr="content: bad argument\n", exit_code=1))

    with pytest.raises(BackendError):
        await ContentService(backend).query_content("emulator-5554", "content://x/y")


@pytest.mark.asyncio
async def test_query_content__garbage_output_does_not_crash() -> None:
    backend = FakeBackend(
        content_query_result=_cr(stdout="\x00 not remotely row output }}}]]]\n")
    )

    result = await ContentService(backend).query_content("emulator-5554", "content://x/y")

    assert result.rows == []


@pytest.mark.asyncio
async def test_query_content__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await ContentService(FakeBackend(unavailable=True)).query_content(
            "emulator-5554", "content://x/y"
        )
