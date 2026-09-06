"""Layer 1 unit tests for the shared dumpsys_package parsers — pure functions,
no backend. Fixture text is transcribed from real `adb shell dumpsys package`
output on a car AVD (a non-shared-uid app and a shared-uid system app), trimmed.
"""

from __future__ import annotations

from adb_automation_mcp.dumpsys_package import (
    find_package_block,
    first_value,
    granted_permission_names,
    package_present,
    parse_bracket_list,
    parse_declared_permissions,
    parse_install_permissions,
    parse_kv,
    parse_requested_permissions,
    parse_runtime_permissions_by_user,
)

# Non-shared-uid app: permission sub-blocks all live inside the Package block.
_APP_DUMP = """\
Activity Resolver Table:
  (irrelevant)

Packages:
  Package [com.example.app] (a1b2c3):
    appId=10234
    codePath=/data/app/~~x==/com.example.app-y==
    versionCode=4500 minSdk=24 targetSdk=34
    versionName=4.5.0
    flags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ALLOW_BACKUP ]
    installerPackageName=com.android.vending
    declared permissions:
      com.example.app.CUSTOM: prot=signature|privileged
      com.example.app.OTHER: prot=signature
    requested permissions:
      android.permission.INTERNET
      android.permission.CAMERA
      android.permission.ACCESS_FINE_LOCATION
    install permissions:
      android.permission.INTERNET: granted=true
      android.permission.ACCESS_NETWORK_STATE: granted=true
    User 0: ceDataInode=1 installed=true hidden=false suspended=false stopped=false enabled=1
      dataDir=/data/user/0/com.example.app
      firstInstallTime=2026-09-01 12:00:00
      runtime permissions:
        android.permission.CAMERA: granted=true, flags=[ USER_SET ]
        android.permission.ACCESS_FINE_LOCATION: granted=false, flags=[ ]
    User 10: ceDataInode=2 installed=true hidden=false suspended=false stopped=false enabled=0
      runtime permissions:
        android.permission.CAMERA: granted=false, flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED ]

Queries:
  something else
"""

# Shared-uid system app: runtime grants live in a later "Shared users:" section.
_SHARED_DUMP = """\
Packages:
  Package [com.android.sys] (dead):
    appId=1000
    versionName=1.0
    requested permissions:
      android.permission.REBOOT
    install permissions:
      android.permission.REBOOT: granted=true
Shared users:
  SharedUser [android.uid.system] (beef):
    User 0:
      gids=[3002]
      runtime permissions:
        android.permission.POST_NOTIFICATIONS: granted=true, flags=[ SYSTEM_FIXED|GRANTED_BY_DEFAULT ]
    User 10:
      runtime permissions:
        android.permission.POST_NOTIFICATIONS: granted=true, flags=[ SYSTEM_FIXED|GRANTED_BY_DEFAULT ]
Dexopt state:
"""


def test_package_present() -> None:
    assert package_present(_APP_DUMP, "com.example.app") is True
    assert package_present("Unable to find package: com.zzz.nope\n", "com.zzz.nope") is False
    assert package_present("nothing here", "com.example.app") is False


def test_find_package_block_bounds_and_first_value() -> None:
    block = find_package_block(_APP_DUMP, "com.example.app")
    assert block is not None
    assert block[0].startswith("  Package [com.example.app]")
    assert not any("Queries:" in ln for ln in block)
    assert first_value(block, "versionName") == "4.5.0"
    assert first_value(block, "codePath") == "/data/app/~~x==/com.example.app-y=="
    assert first_value(block, "nonexistent") is None


def test_find_package_block_missing_returns_none() -> None:
    assert find_package_block(_APP_DUMP, "com.other.app") is None


def test_parse_kv_and_bracket_list() -> None:
    kv = parse_kv("versionCode=4500 minSdk=24 targetSdk=34")
    assert kv == {"versionCode": "4500", "minSdk": "24", "targetSdk": "34"}
    block = find_package_block(_APP_DUMP, "com.example.app")
    assert block is not None
    assert parse_bracket_list(block, "flags") == [
        "HAS_CODE",
        "ALLOW_CLEAR_USER_DATA",
        "ALLOW_BACKUP",
    ]


def test_parse_requested_and_declared_permissions() -> None:
    block = find_package_block(_APP_DUMP, "com.example.app")
    assert block is not None
    assert parse_requested_permissions(block) == [
        "android.permission.INTERNET",
        "android.permission.CAMERA",
        "android.permission.ACCESS_FINE_LOCATION",
    ]
    assert parse_declared_permissions(block) == [
        ("com.example.app.CUSTOM", "signature|privileged"),
        ("com.example.app.OTHER", "signature"),
    ]


def test_parse_install_permissions() -> None:
    block = find_package_block(_APP_DUMP, "com.example.app")
    assert block is not None
    assert parse_install_permissions(block) == [
        ("android.permission.INTERNET", True),
        ("android.permission.ACCESS_NETWORK_STATE", True),
    ]


def test_parse_runtime_permissions_by_user_inside_block() -> None:
    rt = parse_runtime_permissions_by_user(_APP_DUMP)
    assert set(rt) == {0, 10}
    assert rt[0] == [
        ("android.permission.CAMERA", True, ["USER_SET"]),
        ("android.permission.ACCESS_FINE_LOCATION", False, []),
    ]
    assert rt[10] == [
        (
            "android.permission.CAMERA",
            False,
            ["USER_SENSITIVE_WHEN_GRANTED", "USER_SENSITIVE_WHEN_DENIED"],
        )
    ]


def test_parse_runtime_permissions_by_user_shared_uid_section() -> None:
    rt = parse_runtime_permissions_by_user(_SHARED_DUMP)
    assert set(rt) == {0, 10}
    assert rt[0][0] == (
        "android.permission.POST_NOTIFICATIONS",
        True,
        ["SYSTEM_FIXED", "GRANTED_BY_DEFAULT"],
    )


def test_granted_permission_names_dedup_and_order() -> None:
    names = granted_permission_names(_APP_DUMP)
    assert names == [
        "android.permission.INTERNET",
        "android.permission.ACCESS_NETWORK_STATE",
        "android.permission.CAMERA",
    ]


def test_parsers_tolerate_missing_sections() -> None:
    tiny = "Packages:\n  Package [com.x] (aa):\n    versionName=1\n"
    block = find_package_block(tiny, "com.x")
    assert block is not None
    assert parse_requested_permissions(block) == []
    assert parse_declared_permissions(block) == []
    assert parse_install_permissions(block) == []
    assert parse_runtime_permissions_by_user(tiny) == {}
    assert granted_permission_names(tiny) == []
