"""A deterministic, in-memory AdbBackend implementation for tests.

Fixture values passed in must be realistic once methods beyond list_devices are
implemented — a test is only a trustworthy predictor of real behavior if it's
exercised against real-shaped data. For now the unimplemented methods raise
NotImplementedError loudly rather than returning silently-wrong fake data.
"""

from __future__ import annotations

import base64
import shlex

from adb_automation_mcp.backend.protocol import CommandResult, DeviceInfo, ExecOutResult
from adb_automation_mcp.errors import AdbTimeoutError, AdbUnavailableError

# A real, minimal 2x2 RGBA PNG (77 bytes) — the deterministic stand-in for
# `adb exec-out screencap -p` output. Generated once with Python's zlib/struct
# PNG encoder (a genuine, decodable PNG with a valid IHDR/IDAT/IEND), not
# hand-invented byte soup, so tests that parse its dimensions get real answers.
_FAKE_SCREENCAP_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP4z8DwHwyBNBAw/AcAR8oI+FuapL4AAAAASUVORK5CYII="
)


def _echo_resolved_tcp_port(endpoint: str) -> CommandResult:
    """Mirror live `adb forward` / `adb reverse`: echo the resolved tcp port
    number on stdout. `tcp:0` → a deterministic stand-in for an adb-allocated
    ephemeral port; a non-tcp endpoint → empty stdout.
    """
    if endpoint == "tcp:0":
        resolved = "41000"
    elif endpoint.startswith("tcp:"):
        resolved = endpoint.split(":", 1)[1]
    else:
        resolved = ""
    return CommandResult(
        stdout=f"{resolved}\n" if resolved else "", stderr="", exit_code=0, duration_ms=30.0
    )


_PM_ENABLED_STATE_WORDS = {
    "enable": "enabled",
    "disable": "disabled",
    "disable-user": "disabled-user",
    "disable-until-used": "disabled-until-used",
    "default-state": "default",
    "default": "default",
}


def _synthesize_pm_set_enabled(command: str) -> CommandResult:
    """Mirror live `pm enable|disable|disable-user|default-state ... TARGET`:
    a single "Package <target> new state: <state>" line, exit 0.
    """
    tokens = command.split()
    subcmd = tokens[1] if len(tokens) > 1 else ""
    target = tokens[-1] if tokens else ""
    state = _PM_ENABLED_STATE_WORDS.get(subcmd, "default")
    return CommandResult(
        stdout=f"Package {target} new state: {state}\n",
        stderr="",
        exit_code=0,
        duration_ms=70.0,
    )


class FakeBackend:
    """AdbBackend implementation backed by in-memory fixtures instead of a real
    device or adb install — deterministic, fast, and usable in any environment.
    """

    def __init__(
        self,
        devices: list[DeviceInfo] | None = None,
        unavailable: bool = False,
        version_result: CommandResult | None = None,
        wait_for_device_result: CommandResult | None = None,
        wait_for_device_timeout: bool = False,
        kill_server_result: CommandResult | None = None,
        start_server_result: CommandResult | None = None,
        connect_result: CommandResult | None = None,
        disconnect_result: CommandResult | None = None,
        root_result: CommandResult | None = None,
        unroot_result: CommandResult | None = None,
        reboot_result: CommandResult | None = None,
        shell_result: CommandResult | None = None,
        dumpsys_user_result: CommandResult | None = None,
        user_info_result: CommandResult | None = None,
        list_users_result: CommandResult | None = None,
        switch_user_result: CommandResult | None = None,
        start_user_result: CommandResult | None = None,
        is_user_stopped_result: CommandResult | None = None,
        user_state_result: CommandResult | None = None,
        create_user_result: CommandResult | None = None,
        remove_user_result: CommandResult | None = None,
        supports_multiple_users_result: CommandResult | None = None,
        max_users_result: CommandResult | None = None,
        max_running_users_result: CommandResult | None = None,
        headless_system_user_mode_result: CommandResult | None = None,
        visible_background_users_supported_result: CommandResult | None = None,
        visible_background_users_on_default_display_supported_result: CommandResult | None = None,
        read_logs_result: CommandResult | None = None,
        clear_logs_result: CommandResult | None = None,
        get_log_buffer_size_result: CommandResult | None = None,
        pidof_result: CommandResult | None = None,
        package_logs_result: CommandResult | None = None,
        log_session_anchor_result: CommandResult | None = None,
        log_session_stop_result: CommandResult | None = None,
        getprop_result: CommandResult | None = None,
        list_properties_result: CommandResult | None = None,
        getprop_context_result: CommandResult | None = None,
        setprop_result: CommandResult | None = None,
        list_packages_result: CommandResult | None = None,
        pm_path_result: CommandResult | None = None,
        dumpsys_package_result: CommandResult | None = None,
        pm_set_enabled_result: CommandResult | None = None,
        install_result: CommandResult | None = None,
        pm_uninstall_result: CommandResult | None = None,
        pm_install_existing_result: CommandResult | None = None,
        send_broadcast_result: CommandResult | None = None,
        start_activity_result: CommandResult | None = None,
        resolve_activity_result: CommandResult | None = None,
        dumpsys_activity_activities_result: CommandResult | None = None,
        start_service_result: CommandResult | None = None,
        start_foreground_service_result: CommandResult | None = None,
        stop_service_result: CommandResult | None = None,
        dumpsys_activity_services_result: CommandResult | None = None,
        force_stop_result: CommandResult | None = None,
        am_kill_result: CommandResult | None = None,
        ps_result: CommandResult | None = None,
        pidof_names_result: CommandResult | None = None,
        dumpsys_meminfo_result: CommandResult | None = None,
        content_query_result: CommandResult | None = None,
        instrument_result: CommandResult | None = None,
        dropbox_print_result: CommandResult | None = None,
        dropbox_system_anr_result: CommandResult | None = None,
        pull_result: CommandResult | None = None,
        forward_result: CommandResult | None = None,
        forward_list_result: CommandResult | None = None,
        forward_remove_result: CommandResult | None = None,
        reverse_result: CommandResult | None = None,
        reverse_list_result: CommandResult | None = None,
        reverse_remove_result: CommandResult | None = None,
        clear_app_data_result: CommandResult | None = None,
        pm_clear_cache_result: CommandResult | None = None,
        pm_clear_cache_timeout: bool = False,
        rm_cache_result: CommandResult | None = None,
        push_result: CommandResult | None = None,
        exec_out_result: ExecOutResult | None = None,
        input_tap_result: CommandResult | None = None,
        input_swipe_result: CommandResult | None = None,
        input_text_result: CommandResult | None = None,
        input_keyevent_result: CommandResult | None = None,
        uiautomator_dump_result: CommandResult | None = None,
        ui_hierarchy_cat_result: CommandResult | None = None,
        grant_permission_result: CommandResult | None = None,
        revoke_permission_result: CommandResult | None = None,
        get_setting_result: CommandResult | None = None,
        set_setting_result: CommandResult | None = None,
        screenrecord_result: CommandResult | None = None,
        dumpsys_display_result: CommandResult | None = None,
        wm_size_result: CommandResult | None = None,
        wm_density_result: CommandResult | None = None,
        dumpsys_power_result: CommandResult | None = None,
        ip_addr_show_result: CommandResult | None = None,
        ip_route_result: CommandResult | None = None,
        dumpsys_connectivity_result: CommandResult | None = None,
        device_timestamp_result: CommandResult | None = None,
        device_utc_offset_result: CommandResult | None = None,
    ) -> None:
        self._devices = devices or []
        self._unavailable = unavailable
        # Real `adb version` output, captured from an actual run. Modern adb
        # (platform-tools) prints four lines: the bridge protocol version, the
        # platform-tools "Version" line, "Installed as <path>", and (added
        # ~2023) "Running on <os>".
        self._version_result = version_result or CommandResult(
            stdout=(
                "Android Debug Bridge version 1.0.41\n"
                "Version 37.0.0-eng.allaud\n"
                "Installed as /media/allaudin/extusb/out/host/linux-x86/bin/adb\n"
                "Running on Linux 6.8.0-138-generic (x86_64)\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=10.0,
        )
        # `adb -s <serial> wait-for-<transport>-<state>` on success: empty
        # stdout, exit 0, returns as soon as the state is reached (verified live
        # against a running car AVD). wait_for_device_timeout=True simulates the
        # block-until-timeout case (unknown serial, or a state the device never
        # reaches) that the real backend surfaces as AdbTimeoutError.
        self._wait_for_device_result = wait_for_device_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=12.0
        )
        self._wait_for_device_timeout = wait_for_device_timeout
        self._kill_server_result = kill_server_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=5.0
        )
        # Real `adb start-server` output when a server needs starting, captured
        # from an actual run — fixtures should be real-shaped, not hand-invented.
        self._start_server_result = start_server_result or CommandResult(
            stdout="",
            stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            exit_code=0,
            duration_ms=180.0,
        )
        # None (the default) means "build a realistic success message from
        # whatever host:port connect() is actually called with" — see connect()
        # below. A fixed override here is for simulating a specific failure.
        self._connect_result = connect_result
        self._disconnect_result = disconnect_result
        # `adb -s <serial> root` output for the common case: a debuggable
        # build restarting adbd as root for the first time this boot. Shaped
        # on documented adb behavior, not captured from a live rootable
        # device in this environment (none was available) — see
        # restart_adbd_as_root's docstring for the same caveat.
        self._root_result = root_result or CommandResult(
            stdout="restarting adbd as root\n", stderr="", exit_code=0, duration_ms=800.0
        )
        # `adb -s <serial> unroot` output for the common case: adbd currently
        # running as root, being dropped back to shell. Captured from a live
        # rootable emulator (car AVD): "restarting adbd as non root", exit 0.
        # The idempotent "already shell" case prints "adbd not running as root"
        # (also exit 0) — override this fixture to simulate that.
        self._unroot_result = unroot_result or CommandResult(
            stdout="restarting adbd as non root\n", stderr="", exit_code=0, duration_ms=600.0
        )
        # `adb -s <serial> reboot` — silent, exit 0, returns the moment the
        # request is delivered (long before the device is back). Verified live
        # against a car AVD. An unknown serial fails at the adb-client level with
        # "error: device '<serial>' not found", exit 1 — override to simulate.
        self._reboot_result = reboot_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=100.0
        )
        # Real `adb shell am get-current-user` output for the common case (a
        # single-user device, primary/owner user), captured from an actual run.
        self._shell_result = shell_result or CommandResult(
            stdout="0\n", stderr="", exit_code=0, duration_ms=45.0
        )
        # Real `adb shell dumpsys user` output, trimmed to one UserInfo block
        # (the real dump was ~1000 lines covering every user on the device).
        self._dumpsys_user_result = dumpsys_user_result or CommandResult(
            stdout=(
                "Current user: 10\n"
                "\n"
                "Users:\n"
                "  UserInfo{10:Driver:412} serialNo=10 isPrimary=false\n"
                "    Type: android.os.usertype.full.SECONDARY\n"
                "    Flags: 1042 (ADMIN|FULL|INITIALIZED)\n"
                "    State: RUNNING_UNLOCKED\n"
                "    Created: +3d9h55m0s649ms ago\n"
                "    Last logged in: +3d9h54m53s394ms ago\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=90.0,
        )
        # None (the default) means "build a realistic single-user block for
        # whatever user_id user_info() is actually called with" — see shell()
        # below. A fixed override here is for simulating "User N not found".
        self._user_info_result = user_info_result
        # Real `adb shell cmd user list -v` output, captured from an actual run.
        self._list_users_result = list_users_result or CommandResult(
            stdout=(
                "2 users:\n"
                "\n"
                "0: id=0, name=System User, type=system.HEADLESS, "
                "flags=INITIALIZED|PRIMARY|SYSTEM (running)\n"
                "1: id=10, name=Driver, type=full.SECONDARY, "
                "flags=ADMIN|FULL|INITIALIZED (running) (current) (visible)\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=55.0,
        )
        # Real `adb shell am switch-user N` success output: empty stdout, exit 0.
        self._switch_user_result = switch_user_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=100.0
        )
        # `adb shell am start-user [-w] [--display N] USER` — captured live from a
        # car AVD: "Success: user started" on stdout, exit 0. A failure prints
        # "Error: could not start user" and STILL exits 0, so outcome is read
        # from the text, not the exit code — override to simulate that.
        self._start_user_result = start_user_result or CommandResult(
            stdout="Success: user started\n", stderr="", exit_code=0, duration_ms=250.0
        )
        # `adb shell am is-user-stopped USER` — bare "true"/"false" on stdout,
        # exit 0. Captured live: an unknown user id returns "true" (i.e.
        # "stopped"), not an error.
        self._is_user_stopped_result = is_user_stopped_result or CommandResult(
            stdout="false\n", stderr="", exit_code=0, duration_ms=30.0
        )
        # `adb shell am get-started-user-state USER` — the lifecycle token on
        # stdout ("RUNNING_UNLOCKED", "RUNNING_LOCKED", "BOOTING", "STOPPING",
        # ...), exit 0. Captured live; a not-started user prints
        # "User is not started: <id>" (also exit 0).
        self._user_state_result = user_state_result or CommandResult(
            stdout="RUNNING_UNLOCKED\n", stderr="", exit_code=0, duration_ms=30.0
        )
        # Real `adb shell pm create-user NAME` success output, captured from an actual run.
        self._create_user_result = create_user_result or CommandResult(
            stdout="Success: created user id 12\n", stderr="", exit_code=0, duration_ms=400.0
        )
        # Real `adb shell pm remove-user ID` success output, captured from an actual run.
        self._remove_user_result = remove_user_result or CommandResult(
            stdout="Success: removed user\n", stderr="", exit_code=0, duration_ms=350.0
        )
        # The following six fixtures (through
        # _visible_background_users_on_default_display_supported_result) back
        # get_user_capabilities. Shaped on documented `pm`/`cmd user` output
        # conventions, not captured from a live device in this environment
        # (none was available) — same caveat as system_properties' fixtures
        # (see that module's service.py docstring); worth a real-device check
        # before trusting the exact wording.
        #
        # `adb shell pm supports-multiple-users` — a labeled boolean line, the
        # commonly documented wording (not a bare "true"/"false").
        self._supports_multiple_users_result = supports_multiple_users_result or CommandResult(
            stdout="Supports multiple users: true\n", stderr="", exit_code=0, duration_ms=25.0
        )
        # `adb shell pm get-max-users` — bare integer.
        self._max_users_result = max_users_result or CommandResult(
            stdout="4\n", stderr="", exit_code=0, duration_ms=25.0
        )
        # `adb shell pm get-max-running-users` — bare integer.
        self._max_running_users_result = max_running_users_result or CommandResult(
            stdout="4\n", stderr="", exit_code=0, duration_ms=25.0
        )
        # `adb shell cmd user is-headless-system-user-mode` — bare boolean.
        self._headless_system_user_mode_result = headless_system_user_mode_result or CommandResult(
            stdout="false\n", stderr="", exit_code=0, duration_ms=30.0
        )
        # `adb shell cmd user is-visible-background-users-supported` — bare boolean.
        self._visible_background_users_supported_result = (
            visible_background_users_supported_result
            or CommandResult(stdout="false\n", stderr="", exit_code=0, duration_ms=30.0)
        )
        # `adb shell cmd user is-visible-background-users-on-default-display-supported`
        # — bare boolean.
        self._visible_background_users_on_default_display_supported_result = (
            visible_background_users_on_default_display_supported_result
            or CommandResult(stdout="false\n", stderr="", exit_code=0, duration_ms=30.0)
        )
        # Real `adb shell logcat -d -v threadtime -t N -b main` output, captured
        # from an actual run (trimmed).
        self._read_logs_result = read_logs_result or CommandResult(
            stdout=(
                "--------- beginning of main\n"
                "08-26 08:24:26.364   462 11426 E audio_hw_generic_caremu: "
                "mixer_thread_loop error[-1] writing data to pcm\n"
                "08-26 08:24:26.364   462 19519 W audio_hw_generic_caremu: "
                "Not supplying enough data to HAL, expected position 445268478 , only wrote 445264560\n"
                "08-26 08:24:26.374 19797 19820 D EmulatedVehicleHardware: "
                "Set value for property ID: 290459441\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=80.0,
        )
        # Real `adb shell logcat -c -b main` success output: empty stdout, exit 0.
        self._clear_logs_result = clear_logs_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=60.0
        )
        # Real `adb shell logcat -g -b main` output, captured from an actual run.
        self._get_log_buffer_size_result = get_log_buffer_size_result or CommandResult(
            stdout=(
                "main: ring buffer is 2 MiB (1 MiB consumed, 26 MiB readable), "
                "max entry is 5120 B, max payload is 4068 B\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=20.0,
        )
        # Real `adb shell pidof -s PACKAGE` success output for a running package.
        self._pidof_result = pidof_result or CommandResult(
            stdout="19861\n", stderr="", exit_code=0, duration_ms=30.0
        )
        # Real `adb shell logcat -d -v threadtime -t N -b main --pid=PID` output,
        # captured from an actual run (trimmed).
        self._package_logs_result = package_logs_result or CommandResult(
            stdout=(
                "--------- beginning of main\n"
                "08-26 08:24:32.118   725  1221 D WifiNetworkSelector: "
                "About to run SavedNetworkNominator :\n"
                "08-26 08:24:32.119   725  1221 V WifiLastResortWatchdog: "
                "updateAvailableNetworks: size = 0\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=70.0,
        )
        # Real `adb shell logcat -d -t 1 -b main -v epoch` output for
        # start_log_session's anchor probe, captured from an actual run.
        self._log_session_anchor_result = log_session_anchor_result or CommandResult(
            stdout=(
                "--------- beginning of main\n"
                "         1787727659.552   548   548 I adbd    : adbd service "
                "requested 'shell,v2,TERM=xterm-256color,raw:logcat -d -t 1 -b main -v epoch'\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=40.0,
        )
        # Real `adb shell logcat -d -v threadtime -b main -t <anchor>` output
        # for stop_log_session's replay, captured from an actual run (trimmed).
        self._log_session_stop_result = log_session_stop_result or CommandResult(
            stdout=(
                "--------- beginning of main\n"
                "08-26 09:00:59.552   548   548 I adbd    : adbd service requested "
                "'shell,v2,TERM=xterm-256color,raw:logcat -d -t 1 -b main -v epoch'\n"
                "08-26 09:00:59.596   462 11426 E audio_hw_generic_caremu: "
                "mixer_thread_loop error[-1] writing data to pcm\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=90.0,
        )
        # `adb shell getprop NAME` for a typical single-value read. Shaped on
        # toybox getprop's documented output — not captured from a live
        # device in this environment (none was available); flagged for a
        # real-device check, see system_properties/service.py's module docstring.
        self._getprop_result = getprop_result or CommandResult(
            stdout="14\n", stderr="", exit_code=0, duration_ms=15.0
        )
        # `adb shell getprop` (list-all) output shape: "[name]: [value]" per
        # line, an empty value rendered as "[]". Same caveat as above.
        self._list_properties_result = list_properties_result or CommandResult(
            stdout=(
                "[ro.build.version.release]: [14]\n"
                "[ro.build.version.sdk]: [34]\n"
                "[ro.product.model]: [Pixel 7]\n"
                "[persist.sys.timezone]: [America/Los_Angeles]\n"
                "[sys.usb.state]: [mtp,adb]\n"
                "[dalvik.vm.heapsize]: []\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=35.0,
        )
        # `adb shell getprop -Z NAME` — SELinux context via toybox's "-Z"
        # context-query convention. Same caveat as above.
        self._getprop_context_result = getprop_context_result or CommandResult(
            stdout="u:object_r:build_prop:s0\n", stderr="", exit_code=0, duration_ms=15.0
        )
        # `adb shell setprop NAME VALUE` success: empty stdout, exit 0.
        self._setprop_result = setprop_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=25.0
        )
        # `adb shell pm list packages` — one "package:<name>" line per
        # installed package, the well-documented and stable pm output shape.
        # Not captured from a live device in this environment (none was
        # available); flagged for a real-device check, same caveat as
        # system_properties' getprop fixtures above.
        self._list_packages_result = list_packages_result or CommandResult(
            stdout=(
                "package:com.android.chrome\n"
                "package:com.example.thirdparty\n"
                "package:com.android.systemui\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=120.0,
        )
        # `adb shell pm path [--user N] PACKAGE` — one "package:<apk path>" line
        # per APK. The base-only single-line shape was captured live from a car
        # AVD (`pm path com.android.car.settings`); the multi-line split shape
        # here follows PackageManagerShellCommand.runPath()'s documented format
        # (base first, then split_config.* APKs) — no split-installed app was
        # available on that image to capture. An unknown package (or an
        # unavailable user scope) exits 1 with NO output on that build — see
        # PackagesService.get_package_path for how the terse case is classified.
        self._pm_path_result = pm_path_result or CommandResult(
            stdout=(
                "package:/data/app/~~kQ7d==/com.example.thirdparty-Ab3c==/base.apk\n"
                "package:/data/app/~~kQ7d==/com.example.thirdparty-Ab3c==/split_config.en.apk\n"
                "package:/data/app/~~kQ7d==/com.example.thirdparty-Ab3c==/split_config.xxhdpi.apk\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=45.0,
        )
        # `adb shell dumpsys package PACKAGE` — trimmed to the one
        # "Package [<name>]" setting block plus its permission sub-blocks. Field
        # names/shapes (appId, versionCode+minSdk+targetSdk on one line,
        # timeStamp/lastUpdateTime, flags=[ ... ], "requested permissions:" /
        # "install permissions:" / per-user "User N:" install-state line +
        # "runtime permissions:" with "NAME: granted=BOOL, flags=[...]") are all
        # transcribed from live car-AVD output; the package here is synthetic
        # (a Play-installed, non-shared-uid app) so the parser sees an
        # installer, a /data/app codePath, and a mix of granted/denied runtime
        # perms. An unknown package makes dumpsys print
        # "Unable to find package: <name>" and still exit 0 — see
        # PackagesService.get_package_info for how that's classified.
        self._dumpsys_package_result = dumpsys_package_result or CommandResult(
            stdout=(
                "Packages:\n"
                "  Package [com.example.thirdparty] (a1b2c3d):\n"
                "    appId=10234\n"
                "    pkg=Package{deadbeef com.example.thirdparty}\n"
                "    codePath=/data/app/~~kQ7d==/com.example.thirdparty-Ab3c==\n"
                "    versionCode=4500 minSdk=24 targetSdk=34\n"
                "    versionName=4.5.0\n"
                "    splits=[base]\n"
                "    flags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ALLOW_BACKUP ]\n"
                "    timeStamp=2026-09-01 12:00:00\n"
                "    lastUpdateTime=2026-09-03 08:30:00\n"
                "    installerPackageName=com.android.vending\n"
                "    installerPackageUid=10123\n"
                "    signatures=PackageSignatures{1a2b version:3, signatures:[abcd1234], past signatures:[]}\n"
                "    declared permissions:\n"
                "      com.example.thirdparty.CUSTOM: prot=signature\n"
                "    requested permissions:\n"
                "      android.permission.INTERNET\n"
                "      android.permission.ACCESS_NETWORK_STATE\n"
                "      android.permission.CAMERA\n"
                "      android.permission.ACCESS_FINE_LOCATION\n"
                "    install permissions:\n"
                "      android.permission.INTERNET: granted=true\n"
                "      android.permission.ACCESS_NETWORK_STATE: granted=true\n"
                "    User 0: ceDataInode=270565 deDataInode=49330 installed=true hidden=false "
                "suspended=false stopped=false notLaunched=false enabled=1 instant=false "
                "virtual=false quarantined=false\n"
                "      installReason=0\n"
                "      dataDir=/data/user/0/com.example.thirdparty\n"
                "      firstInstallTime=2026-09-01 12:00:00\n"
                "    User 0:\n"
                "      gids=[3003]\n"
                "      runtime permissions:\n"
                "        android.permission.CAMERA: granted=true, flags=[ USER_SET ]\n"
                "        android.permission.ACCESS_FINE_LOCATION: granted=false, flags=[ ]\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=120.0,
        )
        # `adb shell pm enable|disable|disable-user|default-state [--user N] TARGET`
        # — on success prints a single "Package <target> new state: <state>" line
        # (verified live on a car AVD: `enabled`, `disabled-user`, `default`).
        # None (the default) means "synthesize that line from whatever subcommand
        # + target shell() is actually called with" — see shell() below. A fixed
        # override simulates a failure (SecurityException stack trace, "Unknown
        # package", etc.).
        self._pm_set_enabled_result = pm_set_enabled_result
        # `adb install [flags] apk_path` — the well-documented, long-stable
        # "Performing Streamed Install" / "Success" wording modern adb uses
        # for a normal install. Not captured from a live device in this
        # environment (none was available); flagged for a real-device
        # check, same caveat as list_packages_result above.
        self._install_result = install_result or CommandResult(
            stdout="Performing Streamed Install\nSuccess\n", stderr="", exit_code=0, duration_ms=900.0
        )
        # `adb shell pm uninstall [-k] [--user ID] [--versionCode CODE]
        # PACKAGE` — PackageManagerShellCommand's documented bare "Success"
        # on success. Same caveat as install_result above.
        self._pm_uninstall_result = pm_uninstall_result or CommandResult(
            stdout="Success\n", stderr="", exit_code=0, duration_ms=200.0
        )
        # None (the default) means "build a realistic 'Package NAME
        # installed for user: ID' success message from whatever
        # package/user_id install_existing_for_user() is actually called
        # with" — see shell() below, same convention as connect_result. A
        # fixed override here is for simulating a specific failure. Same
        # caveat as install_result above.
        self._pm_install_existing_result = pm_install_existing_result
        # `adb shell am broadcast` — the well-documented, long-stable
        # AOSP `Am.java` output shape ("Broadcasting: Intent { ... }" then
        # "Broadcast completed: result=N"). Not captured from a live device
        # in this environment (none was available); same caveat as
        # root_result/list_packages_result above.
        self._send_broadcast_result = send_broadcast_result or CommandResult(
            stdout=(
                "Broadcasting: Intent { act=android.intent.action.MY_ACTION }\n"
                "Broadcast completed: result=0\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=150.0,
        )
        # `adb shell am start` without `-W` — the well-documented, long-stable
        # AOSP `Am.java` output shape for a normal (non-waited) launch: just
        # the "Starting: Intent { ... }" line, no completion/status detail.
        # Not captured from a live device in this environment (none was
        # available); same caveat as send_broadcast_result above.
        self._start_activity_result = start_activity_result or CommandResult(
            stdout="Starting: Intent { cmp=com.example.app/.MainActivity }\n",
            stderr="",
            exit_code=0,
            duration_ms=200.0,
        )
        # `adb shell cmd package resolve-activity --brief ...` — captured live
        # from a car AVD: a "priority=... match=0x... isDefault=..." metadata
        # line, then the resolved "<package>/<class>" on its own line. `cmd`
        # always exits 0; "No activity found" is how a non-match is reported,
        # and a malformed -n component yields a "Bad component name" stack trace
        # (also exit 0) — see ActivitiesService.resolve_activity.
        self._resolve_activity_result = resolve_activity_result or CommandResult(
            stdout=(
                "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n"
                "com.android.car.carlauncher/.CarLauncher\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=90.0,
        )
        # `adb shell dumpsys activity activities` — trimmed to the markers
        # ActivitiesService.get_foreground_activity parses: a "Display #N"
        # header, per-task "topResumedActivity=ActivityRecord{...}", the
        # root-scope "ResumedActivity: ActivityRecord{...}", and window state's
        # "mFocusedApp=ActivityRecord{...}". Field shapes captured live from a
        # car AVD (single display, launcher in foreground, user 10).
        self._dumpsys_activity_activities_result = dumpsys_activity_activities_result or CommandResult(
            stdout=(
                "ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)\n"
                "Display #0 (activities from top to bottom):\n"
                "  * Task{a6084dc #1 type=home U=0 visible=true}\n"
                "    * Task{b76de50 #1000004 type=home A=1010050:com.android.car.carlauncher U=10}\n"
                "      isSleeping=false\n"
                "      topResumedActivity=ActivityRecord{138464275 u10 "
                "com.android.car.carlauncher/.CarLauncher t1000004}\n"
                "      * Hist  #0: ActivityRecord{138464275 u10 "
                "com.android.car.carlauncher/.CarLauncher t1000004}\n"
                "        packageName=com.android.car.carlauncher\n"
                "\n"
                "  ResumedActivity: ActivityRecord{138464275 u10 "
                "com.android.car.carlauncher/.CarLauncher t1000004}\n"
                "\n"
                "ActivityTaskSupervisor state:\n"
                "  topDisplayFocusedRootTask=Task{a6084dc #1 type=home}\n"
                "  mCurrentFocus=Window{f78bd34 u10 "
                "com.android.car.carlauncher/com.android.car.carlauncher.CarLauncher}\n"
                "  mFocusedApp=ActivityRecord{138464275 u10 "
                "com.android.car.carlauncher/.CarLauncher t1000004}\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=180.0,
        )
        # `adb shell am start-service` — the well-documented, long-stable
        # AOSP `Am.java`/`runStartService` output shape for a normal start:
        # just the "Starting service: Intent { ... }" line. Not captured
        # from a live device in this environment (none was available); same
        # caveat as start_activity_result above.
        self._start_service_result = start_service_result or CommandResult(
            stdout="Starting service: Intent { cmp=com.example.app/.MyService }\n",
            stderr="",
            exit_code=0,
            duration_ms=140.0,
        )
        # `adb shell am start-foreground-service` — same "Starting service:
        # Intent { ... }" line, no "Error:" line, exit 0 on success (verified
        # live on a car AVD against com.android.systemui/.SystemUIService). A
        # well-formed component with no matching service still exits 0 with an
        # "Error: Not found; no service started." line; a malformed -n yields a
        # "Bad component name" stack trace (also exit 0).
        self._start_foreground_service_result = start_foreground_service_result or CommandResult(
            stdout="Starting service: Intent { cmp=com.example.app/.MyFgService }\n",
            stderr="",
            exit_code=0,
            duration_ms=150.0,
        )
        # `adb shell am stop-service` — "Stopping service: Intent { ... }" then
        # "Service stopped" (success, exit 0) or "Service not stopped: was not
        # running." (exit 255 on the car AVD; still a valid outcome). Default
        # fixture: the running-and-stopped path.
        self._stop_service_result = stop_service_result or CommandResult(
            stdout=(
                "Stopping service: Intent { cmp=com.example.app/.MyService }\n"
                "Service stopped\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=110.0,
        )
        # `adb shell dumpsys activity services <component>` — the filtered
        # "User N active services:" / "* ServiceRecord{<hash> uN <component>
        # c:...}" blocks, trimmed to the fields get_service_status parses. Field
        # shapes (packageName=, processName=, app=ProcessRecord{<pid>:pkg/uid},
        # isForeground=... foregroundId=..., startForegroundCount=,
        # startRequested=... callStart=... lastStartId=, createdFromFg=) are
        # transcribed from live car-AVD output for a foreground service. An
        # unknown/absent service prints "No services match: <component>" and
        # still exits 0 — see AndroidServicesService.get_service_status.
        self._dumpsys_activity_services_result = dumpsys_activity_services_result or CommandResult(
            stdout=(
                "ACTIVITY MANAGER SERVICES (dumpsys activity services)\n"
                "  User 0 active services:\n"
                "  * ServiceRecord{700fb2f u0 com.example.app/.MyFgService c:com.example.app}\n"
                "    intent={cmp=com.example.app/.MyFgService}\n"
                "    packageName=com.example.app\n"
                "    processName=com.example.app\n"
                "    app=ProcessRecord{7ff9d4b 1884:com.example.app/u0a61}\n"
                "    startForegroundCount=1\n"
                "    isForeground=true foregroundId=1 types=0x00000008 "
                "foregroundNoti=Notification(channel=default)\n"
                "    createTime=-9h37m29s140ms startingBgTimeout=--\n"
                "    lastActivity=-9h37m29s87ms restartTime=-9h37m29s138ms createdFromFg=false\n"
                "    startRequested=true delayedStop=false stopIfKilled=false callStart=true "
                "lastStartId=2\n"
                "\n"
                "  User 10 active services:\n"
                "  * ServiceRecord{e0b3c75 u10 com.example.app/.MyFgService c:com.example.app}\n"
                "    packageName=com.example.app\n"
                "    processName=com.example.app\n"
                "    app=ProcessRecord{1a2b3c 1885:com.example.app/u10a61}\n"
                "    isForeground=false\n"
                "    startRequested=true callStart=true lastStartId=1\n"
                "    createdFromFg=true\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=170.0,
        )
        # `adb shell am force-stop` — the well-documented, long-stable AOSP
        # behavior: no stdout at all on success. Not captured from a live
        # device in this environment (none was available); same caveat as
        # start_service_result above.
        self._force_stop_result = force_stop_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=90.0
        )
        # `adb shell am kill [--user N] PACKAGE` — ActivityManagerShellCommand's
        # runKill(): no stdout at all, exit 0, whether or not any killable
        # background process actually existed (verified live on a car AVD, incl.
        # for a package that isn't installed). Override to simulate a failure.
        self._am_kill_result = am_kill_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=70.0
        )
        # `adb shell ps -A -o PID,PPID,USER,RSS,NAME` — toybox `ps`: a fixed
        # header line then one space-padded, column-aligned row per process.
        # Rows captured live from a car AVD (init, a kernel worker thread with a
        # bracketed name and RSS 0, and a running app process). Override to
        # exercise filter / malformed-output paths.
        self._ps_result = ps_result or CommandResult(
            stdout=(
                "  PID  PPID USER            RSS NAME\n"
                "    1     0 root          14776 init\n"
                "    2     0 root              0 [kthreadd]\n"
                " 1224   432 u0_a141      260040 com.android.systemui\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=110.0,
        )
        # `adb shell pidof NAME` (no `-s`) — space-separated PID list on one
        # line, exit 0, when at least one process matches; empty stdout and
        # exit 1 when none do (a valid "not running" outcome, not an error).
        # Verified live on a car AVD. Override to simulate the multi-PID or
        # not-running cases.
        self._pidof_names_result = pidof_names_result or CommandResult(
            stdout="1224\n", stderr="", exit_code=0, duration_ms=25.0
        )
        # `adb shell dumpsys meminfo -s PACKAGE_OR_PID` — trimmed to the
        # markers ProcessesService.get_process_memory reads: the "** MEMINFO in
        # pid N [name] **" header and the "App Summary" Pss/Rss table with its
        # "TOTAL PSS: / TOTAL RSS: / TOTAL SWAP (KB):" line. Field shapes
        # transcribed from live car-AVD output for com.android.systemui. A
        # target with no running process prints "No process found for: <target>"
        # and still exits 0 — see get_process_memory for how that's classified.
        # `adb shell content query --uri URI [...]` — one "Row: N col=val, col=val"
        # line per row (captured live from content://settings/system on a car
        # AVD). An empty result set prints "No result found." and exits 0; a bad
        # authority prints "Error while accessing provider:<a>" + a Java stack
        # trace and STILL exits 0 — override to simulate those.
        self._content_query_result = content_query_result or CommandResult(
            stdout=(
                "Row: 0 _id=19, name=notification_light_pulse, value=1\n"
                "Row: 1 _id=4, name=volume_alarm, value=6\n"
                "Row: 2 _id=0, name=volume_music, value=5\n"
                "Row: 3 _id=38, name=ringtone, "
                "value=content://media/internal/audio/media/139?title=Girtab&canonical=1\n"
                "Row: 4 _id=40, name=unset_key, value=NULL\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=120.0,
        )
        # `adb shell am instrument -w -r [...] COMPONENT` — the raw
        # INSTRUMENTATION_STATUS / INSTRUMENTATION_STATUS_CODE / _RESULT / _CODE
        # marker stream. Default fixture: a two-test all-pass run shaped on the
        # documented AndroidJUnitRunner raw output (no instrumentation package
        # was installed on the car AVD to capture from). A component that can't
        # be started prints "INSTRUMENTATION_FAILED: <component>" + a stack
        # trace and exits 0 — override to simulate that.
        self._instrument_result = instrument_result or CommandResult(
            stdout=(
                "INSTRUMENTATION_STATUS: class=com.example.FooTest\n"
                "INSTRUMENTATION_STATUS: current=1\n"
                "INSTRUMENTATION_STATUS: id=AndroidJUnitRunner\n"
                "INSTRUMENTATION_STATUS: numtests=2\n"
                "INSTRUMENTATION_STATUS: stream=\n"
                "INSTRUMENTATION_STATUS: test=testAlpha\n"
                "INSTRUMENTATION_STATUS_CODE: 1\n"
                "INSTRUMENTATION_STATUS: class=com.example.FooTest\n"
                "INSTRUMENTATION_STATUS: current=1\n"
                "INSTRUMENTATION_STATUS: numtests=2\n"
                "INSTRUMENTATION_STATUS: stream=.\n"
                "INSTRUMENTATION_STATUS: test=testAlpha\n"
                "INSTRUMENTATION_STATUS_CODE: 0\n"
                "INSTRUMENTATION_STATUS: class=com.example.FooTest\n"
                "INSTRUMENTATION_STATUS: current=2\n"
                "INSTRUMENTATION_STATUS: numtests=2\n"
                "INSTRUMENTATION_STATUS: test=testBeta\n"
                "INSTRUMENTATION_STATUS_CODE: 1\n"
                "INSTRUMENTATION_STATUS: current=2\n"
                "INSTRUMENTATION_STATUS: numtests=2\n"
                "INSTRUMENTATION_STATUS: stream=..\n"
                "INSTRUMENTATION_STATUS: test=testBeta\n"
                "INSTRUMENTATION_STATUS_CODE: 0\n"
                "INSTRUMENTATION_RESULT: stream=\n"
                "\n"
                "Time: 1.234\n"
                "\n"
                "OK (2 tests)\n"
                "\n"
                "INSTRUMENTATION_CODE: -1\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=1800.0,
        )
        # `adb shell dumpsys dropbox --print data_app_anr` — the DropBox
        # preamble, then one `====`-delimited entry per record: a "<timestamp>
        # <tag> (text, N bytes)" header line, a `Key: value` header block, a
        # blank line, then the body (the `Subject:` line lives in the body, not
        # the header block — verified live on a car AVD). Two entries for
        # com.example.app plus one for a different package, so package filtering
        # is exercised. `--print` takes ONE tag, so the service also issues a
        # `... system_app_anr` call — see _dropbox_system_anr_result. Override
        # to simulate the "(No entries found.)" empty case or a failure.
        self._dropbox_print_result = dropbox_print_result or CommandResult(
            stdout=(
                "Drop box contents: 1000 entries\n"
                "Max entries: 1000\n"
                "Low priority rate limit period: 2000 ms\n"
                "Low priority tags: {data_app_wtf, system_app_strictmode}\n"
                "Searching for: data_app_anr\n"
                "\n"
                "========================================\n"
                "2026-09-06 16:50:01 data_app_anr (text, 1180 bytes)\n"
                "Process: com.example.app\n"
                "PID: 12345\n"
                "UID: 10234\n"
                "Flags: 0x30c8be45\n"
                "Package: com.example.app v450 (4.5.0)\n"
                "Build: Android/sdk_car_x86_64/emulator_car64_x86_64:Baklava/CP2A.260605.016/"
                "eng.allaud:userdebug/test-keys\n"
                "\n"
                "Subject: ANR in com.example.app (com.example.app/.MainActivity)\n"
                "PID: 12345\n"
                "Reason: Input dispatching timed out "
                "(e39a3f8 com.example.app/.MainActivity, 5007.7ms elapsed)\n"
                "Load: 3.1 / 2.8 / 2.5\n"
                "\n"
                '"main" prio=5 tid=1 Blocked\n'
                "  | group=\"main\" sCount=1 ucsCount=0 flags=1 obj=0x72c8d418 self=0xb400007cf...\n"
                "  at com.example.app.MainActivity.onResume(MainActivity.java:88)\n"
                "  - waiting to lock <0x0abc1234> held by thread 12\n"
                "  at android.app.Activity.performResume(Activity.java:8944)\n"
                "\n"
                "========================================\n"
                "2026-09-06 16:52:25 data_app_anr (text, 1042 bytes)\n"
                "Process: com.example.app\n"
                "PID: 12777\n"
                "UID: 10234\n"
                "Flags: 0x30c8be45\n"
                "Package: com.example.app v450 (4.5.0)\n"
                "\n"
                "Subject: ANR in com.example.app (com.example.app/.DetailActivity)\n"
                "Reason: executing service com.example.app/.SyncService\n"
                "\n"
                '"main" prio=5 tid=1 Native\n'
                "  at libcore.io.Linux.read(Native Method)\n"
                "  at com.example.app.SyncService.blockingCall(SyncService.java:210)\n"
                "\n"
                "========================================\n"
                "2026-09-06 16:40:10 data_app_anr (text, 900 bytes)\n"
                "Process: com.other.app\n"
                "PID: 20001\n"
                "UID: 10250\n"
                "Flags: 0x30c8be45\n"
                "Package: com.other.app v10 (1.0)\n"
                "\n"
                "Subject: ANR in com.other.app\n"
                '"main" prio=5 tid=1 Suspended\n'
                "  at com.other.app.Foo.bar(Foo.java:5)\n"
                "\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=140.0,
        )
        # `adb shell dumpsys dropbox --print system_app_anr` — the default has no
        # system-app ANR entries (the sample data lives under data_app_anr).
        self._dropbox_system_anr_result = dropbox_system_anr_result or CommandResult(
            stdout=(
                "Drop box contents: 1000 entries\n"
                "Searching for: system_app_anr\n"
                "\n"
                "(No entries found.)\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=90.0,
        )
        self._dumpsys_meminfo_result = dumpsys_meminfo_result or CommandResult(
            stdout=(
                "Applications Memory Usage (in Kilobytes):\n"
                "Uptime: 539397 Realtime: 539397\n"
                "\n"
                "** MEMINFO in pid 1224 [com.android.systemui] **\n"
                "\n"
                " App Summary\n"
                "                       Pss(KB)                        Rss(KB)\n"
                "                        ------                         ------\n"
                "           Java Heap:    28048                          59716\n"
                "         Native Heap:    21120                          24912\n"
                "                Code:    37168                         172148\n"
                "               Stack:     1632                           1640\n"
                "            Graphics:        0                              0\n"
                "       Private Other:     4008\n"
                "              System:    13345\n"
                "             Unknown:                                   10000\n"
                "\n"
                "           TOTAL PSS:   105321            TOTAL RSS:   268416"
                "      TOTAL SWAP (KB):        0\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=210.0,
        )
        # None (the default) means "build a realistic success message from
        # whatever remote_path is actually pulled" — see pull() below, same
        # convention as connect_result. Real, long-stable `adb pull` wording.
        self._pull_result = pull_result
        # None (the default) means "echo back the resolved local port on stdout
        # for whatever local endpoint forward() is called with" — see forward()
        # below. `adb forward` was verified live (car AVD) to print the local
        # port number even for an explicit `tcp:<n>` local, and the
        # adb-allocated port for `tcp:0`. A fixed override simulates a failure
        # ("cannot rebind existing socket", "bad port number", etc.).
        self._forward_result = forward_result
        # `adb forward --list` — one "<serial> <local> <remote>" line per active
        # host→device forward, server-global. Captured live (car AVD), with a
        # second row hand-shaped to a non-tcp endpoint kind so parsing of
        # "multiple endpoint types" is exercised by default.
        self._forward_list_result = forward_list_result or CommandResult(
            stdout=(
                "emulator-5554 tcp:6100 tcp:8080\n"
                "emulator-5554 tcp:43177 localabstract:foo\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=25.0,
        )
        # `adb -s <serial> forward --remove <local>` — silent on success, exit 0
        # (verified live). A missing listener is "adb: error: listener '<x>' not
        # found", exit 1 — override this fixture to simulate that.
        self._forward_remove_result = forward_remove_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=15.0
        )
        # None (the default) means "echo back the resolved remote port on stdout
        # for whatever remote endpoint reverse() is called with" — see reverse()
        # below, same convention as forward(). Verified live on the car AVD.
        self._reverse_result = reverse_result
        # `adb -s <serial> reverse --list` — one "<transport-token> <remote>
        # <local>" line per active device→host reverse. Note column 0 is a
        # "host-<N>" transport token, NOT the serial (verified live).
        self._reverse_list_result = reverse_list_result or CommandResult(
            stdout=(
                "host-15 tcp:8080 tcp:7000\n"
                "host-15 localabstract:bar tcp:7001\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=25.0,
        )
        # `adb -s <serial> reverse --remove <remote>` — silent on success, exit
        # 0 (verified live). Missing listener → "adb: error: listener '<x>' not
        # found", exit 1.
        self._reverse_remove_result = reverse_remove_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=15.0
        )
        # `adb shell pm clear` — PackageManagerShellCommand's documented,
        # long-stable success text: a bare "Success". Not captured from a
        # live device in this environment (none was available); same caveat
        # as force_stop_result above.
        self._clear_app_data_result = clear_app_data_result or CommandResult(
            stdout="Success\n", stderr="", exit_code=0, duration_ms=110.0
        )
        # `adb shell pm clear --cache-only [--user N] PACKAGE` — same
        # "Success"/"Failed" wording as an unscoped clear on a build that
        # supports it. NOTE: the car AVD this project targets *hangs*
        # indefinitely on this command (a build bug), so real runs surface as
        # AdbTimeoutError — see AppDataService.clear_app_cache. Override with a
        # non-zero result to simulate the "--cache-only not supported" case.
        self._pm_clear_cache_result = pm_clear_cache_result or CommandResult(
            stdout="Success\n", stderr="", exit_code=0, duration_ms=120.0
        )
        self._pm_clear_cache_timeout = pm_clear_cache_timeout
        # `rm -rf <per-user cache dirs>` — the fallback when `pm clear
        # --cache-only` is unsupported/hangs. Silent on success (exit 0) as
        # root; "Permission denied" (exit 1) when adbd isn't root. Verified live
        # on a car AVD.
        self._rm_cache_result = rm_cache_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=40.0
        )
        # `adb push LOCAL REMOTE` — real wording: "<local>: 1 file pushed, 0
        # skipped. <rate> (<n> bytes in <t>s)". Captured live from a car AVD.
        self._push_result = push_result or CommandResult(
            stdout=(
                "/host/file: 1 file pushed, 0 skipped. 0.0 MB/s (3 bytes in 0.000s)\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=90.0,
        )
        # `input swipe`/`input text`/`input keyevent` — all silent on success
        # (no stdout), exit 0. Captured live from a car AVD.
        self._input_swipe_result = input_swipe_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=50.0
        )
        self._input_text_result = input_text_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=45.0
        )
        self._input_keyevent_result = input_keyevent_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=40.0
        )
        # `adb exec-out screencap -p` — streams the raw PNG on stdout, nothing
        # on stderr, exit 0. The default fixture is a real (tiny) PNG; see
        # _FAKE_SCREENCAP_PNG above.
        self._exec_out_result = exec_out_result or ExecOutResult(
            stdout=_FAKE_SCREENCAP_PNG, stderr="", exit_code=0, duration_ms=250.0
        )
        # `input tap x y` — real behavior is silent on success (no stdout).
        # Not captured from a live device in this environment (none was
        # available); same caveat as exec_out_result above.
        self._input_tap_result = input_tap_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=45.0
        )
        # `uiautomator dump <path>` — real, long-stable success wording. Not
        # captured from a live device in this environment (none was
        # available); same caveat as input_tap_result above.
        self._uiautomator_dump_result = uiautomator_dump_result or CommandResult(
            stdout="UI hierarchy dumped to: /data/local/tmp/window_dump.xml\n",
            stderr="",
            exit_code=0,
            duration_ms=850.0,
        )
        # `cat <dumped xml path>` — a small, real-shaped uiautomator hierarchy
        # (the well-documented, long-stable `<hierarchy>`/`<node>` schema).
        # Not captured from a live device in this environment (none was
        # available); same caveat as uiautomator_dump_result above.
        self._ui_hierarchy_cat_result = ui_hierarchy_cat_result or CommandResult(
            stdout=(
                "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                '<hierarchy rotation="0">'
                '<node index="0" text="" resource-id="" class="android.widget.FrameLayout" '
                'package="com.android.launcher3" content-desc="" checkable="false" checked="false" '
                'clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" '
                'long-clickable="false" password="false" selected="false" bounds="[0,0][1080,2400]">'
                '<node index="0" text="Phone" resource-id="com.android.launcher3:id/icon" '
                'class="android.widget.TextView" package="com.android.launcher3" content-desc="Phone" '
                'checkable="false" checked="false" clickable="true" enabled="true" focusable="true" '
                'focused="false" scrollable="false" long-clickable="true" password="false" '
                'selected="false" bounds="[100,200][300,400]" />'
                "</node>"
                "</hierarchy>"
            ),
            stderr="",
            exit_code=0,
            duration_ms=20.0,
        )
        # `pm grant PACKAGE PERMISSION` — real behavior is silent on success
        # (no stdout). Not captured from a live device in this environment
        # (none was available); same caveat as ui_hierarchy_cat_result above.
        self._grant_permission_result = grant_permission_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=60.0
        )
        # `pm revoke [--user N] PACKAGE PERMISSION` — verified live on a car AVD:
        # silent, exit 0 on success, and idempotent (revoking an already-revoked
        # or not-requested runtime permission is also silent + exit 0). Failure
        # modes surface as a Java stack trace / "Failure [reason]" line on a
        # non-zero exit — see PermissionsService._raise_for_grant_failure.
        self._revoke_permission_result = revoke_permission_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=60.0
        )
        # `settings get NAMESPACE KEY` — a typical set value. Not captured
        # from a live device in this environment (none was available); same
        # caveat as grant_permission_result above.
        self._get_setting_result = get_setting_result or CommandResult(
            stdout="128\n", stderr="", exit_code=0, duration_ms=40.0
        )
        # `settings [--user N] put NAMESPACE KEY VALUE` — SettingsProvider is
        # silent on success, exit 0 (verified live on a car AVD). A protected
        # namespace/key surfaces as a SecurityException stack trace on a
        # non-zero exit — override this fixture to simulate that.
        self._set_setting_result = set_setting_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=45.0
        )
        # In-memory SettingsProvider stand-in: `put` records here, `get` reads
        # back from here (falling through to _get_setting_result when a key was
        # never written this session), so set_setting round-trip tests see the
        # value they wrote. Keyed by "<namespace>/<key>".
        self._settings_store: dict[str, str] = {}
        # `screenrecord [options] REMOTE` — silent on success, exit 0, blocks
        # for the whole --time-limit; `--verbose` adds progress lines on stdout.
        # Captured live from a car AVD. A failure (encoder init, unwritable
        # path) surfaces on stderr at a non-zero exit — override to simulate.
        self._screenrecord_result = screenrecord_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=3000.0
        )
        # `dumpsys display` — a real dump is hundreds of lines; trimmed to the
        # markers DisplaysService.list_displays parses: the "mViewports=[...]"
        # line (one DisplayViewport{...} per active viewport) and the
        # "Display States:" section ("Display Id=N" / "Display State=ON").
        # Field shapes transcribed from live car-AVD output (single INTERNAL
        # display, 1408x792, 160dpi); the second viewport row is hand-shaped to
        # an EXTERNAL display so multi-display parsing is exercised by default.
        self._dumpsys_display_result = dumpsys_display_result or CommandResult(
            stdout=(
                "DISPLAY MANAGER (dumpsys display)\n"
                "  mViewports=[DisplayViewport{type=INTERNAL, valid=true, isActive=true, "
                "displayId=0, uniqueId='local:4619827259835644672', physicalPort=0, "
                "orientation=0, densityDpi=160, xDpi=160.0, yDpi=160.0, "
                "logicalFrame=Rect(0, 0 - 1408, 792), physicalFrame=Rect(0, 0 - 1408, 792), "
                "deviceWidth=1408, deviceHeight=792}, DisplayViewport{type=EXTERNAL, "
                "valid=true, isActive=true, displayId=2, uniqueId='local:4619827259835644673', "
                "physicalPort=1, orientation=0, densityDpi=213, xDpi=213.0, yDpi=213.0, "
                "logicalFrame=Rect(0, 0 - 1920, 1080), physicalFrame=Rect(0, 0 - 1920, 1080), "
                "deviceWidth=1920, deviceHeight=1080}]\n"
                "  mStableDisplaySize=Point(1408, 792)\n"
                "\n"
                "Display States: size=2\n"
                "---------------------\n"
                "  Display Id=0\n"
                "  Display State=ON\n"
                "  Display Brightness=0.39763778\n"
                "  Display Id=2\n"
                "  Display State=OFF\n"
                "  Display Brightness=0.0\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=160.0,
        )
        # `wm size` / `wm size -d N` — WindowManagerShellCommand's long-stable
        # wording: "Physical size: WxH", plus a second "Override size: WxH" line
        # only when an override is in effect. Verified live on a car AVD (a
        # non-existent display id prints "Physical size: 0x0", exit 0). Override
        # this fixture to exercise the override-present path.
        self._wm_size_result = wm_size_result or CommandResult(
            stdout="Physical size: 1408x792\n", stderr="", exit_code=0, duration_ms=30.0
        )
        # `wm density` / `wm density -d N` — "Physical density: N", plus
        # "Override density: N" only when overridden. Verified live on a car AVD
        # (a non-existent display id prints "Physical density: -1", exit 0).
        self._wm_density_result = wm_density_result or CommandResult(
            stdout="Physical density: 160\n", stderr="", exit_code=0, duration_ms=30.0
        )
        # `dumpsys power` — a real dump is hundreds of lines; trimmed to the
        # PowerManagerService block this module actually parses. Shaped on
        # PowerManagerService.dump()'s documented, long-stable field names.
        # Not captured from a live device in this environment (none was
        # available); same caveat as get_setting_result above.
        self._dumpsys_power_result = dumpsys_power_result or CommandResult(
            stdout=(
                "Power Manager State:\n"
                "  mDirty=0x0\n"
                "  mWakefulness=Awake\n"
                "  mWakefulnessChanging=false\n"
                "  mWakeLockSummary=0x0\n"
                "  mUserActivitySummary=0x1\n"
                "  mSandmanScheduled=false\n"
                "  mLastWakeTime=52611994516 ago\n"
                "  mLastSleepTime=0 ago\n"
                "  mSystemReady=true\n"
                "  mBootCompleted=true\n"
                "  mIsPowered=true\n"
                "  mPlugType=2\n"
                "  mBatteryLevel=100\n"
                "  mDockState=0\n"
                "  mStayOn=false\n"
                "  mProximityPositive=false\n"
                "  mInteractive=true\n"
                "  mScreenBrightnessBoostInProgress=false\n"
                "  mDisplayReady=true\n"
                "  mHoldingWakeLockSuspendBlocker=true\n"
                "  mHoldingDisplaySuspendBlocker=true\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=180.0,
        )
        # `ip addr show` — a loopback plus one wlan interface with an IPv4
        # and IPv6 address, plus one down interface with no addresses.
        # Real, long-stable iproute2 output shape. Not captured from a live
        # device in this environment (none was available); same caveat as
        # dumpsys_power_result above.
        self._ip_addr_show_result = ip_addr_show_result or CommandResult(
            stdout=(
                "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000\n"
                "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
                "    inet 127.0.0.1/8 scope host lo\n"
                "       valid_lft forever preferred_lft forever\n"
                "    inet6 ::1/128 scope host \n"
                "       valid_lft forever preferred_lft forever\n"
                "2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000\n"
                "    link/ether 02:00:00:00:00:00 brd ff:ff:ff:ff:ff:ff\n"
                "    inet 192.168.1.100/24 brd 192.168.1.255 scope global wlan0\n"
                "       valid_lft forever preferred_lft forever\n"
                "    inet6 fe80::abcd:1234:5678:9abc/64 scope link \n"
                "       valid_lft forever preferred_lft forever\n"
                "3: rmnet_data0: <NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000\n"
                "    link/none \n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=60.0,
        )
        # `ip route` — one route per line, first token the destination
        # ("default" or a CIDR) followed by ` key value` pairs (via/dev/proto/
        # scope/src/metric). Captured live from a car AVD (a single on-link
        # route, no default). Override to exercise default-route / metric
        # parsing.
        self._ip_route_result = ip_route_result or CommandResult(
            stdout="10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15\n",
            stderr="",
            exit_code=0,
            duration_ms=25.0,
        )
        # `dumpsys connectivity` — a real dump is hundreds of lines; trimmed to
        # the markers ConnectivityService.get_connectivity_state reads: the
        # "Active default network: N" line and the "Current Networks:" section's
        # per-network "NetworkAgentInfo{network{N} ... ni{TYPE STATE ...} ...
        # nc{[ Transports: ... Capabilities: ... ]} ...}" line. Field shapes
        # transcribed from live car-AVD output (a validated CELLULAR default
        # network).
        self._dumpsys_connectivity_result = dumpsys_connectivity_result or CommandResult(
            stdout=(
                "Active default network: 100\n"
                "\n"
                "Current Networks:\n"
                "  NetworkAgentInfo{network{100}  handle{432902426637}  "
                "ni{MOBILE[NR] CONNECTED extra: epc.tmobile.com} "
                "created=2026-09-06T18:36:11.660Z Score(Policies : IS_VALIDATED ; KeepConnected : 0)  "
                "lp{{InterfaceName: eth0 LinkAddresses: [ 10.0.2.15/24 ] Routes: [ 0.0.0.0/0 -> 10.0.2.2 eth0 ]}}  "
                "nc{[ Transports: CELLULAR Capabilities: "
                "INTERNET&NOT_RESTRICTED&TRUSTED&NOT_VPN&VALIDATED&NOT_ROAMING&FOREGROUND&NOT_CONGESTED"
                "&NOT_SUSPENDED&NOT_VCN_MANAGED LinkUpBandwidth>=60000Kbps LinkDnBandwidth>=145000Kbps "
                "SubscriptionIds: {1} UnderlyingNetworks: Null]}  factorySerialNumber=5}\n"
                "    Nat464Xlat:\n"
                "      <not started>\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=200.0,
        )
        # `date +%Y-%m-%dT%H:%M:%S` / `date +%z` — toybox `date`'s documented
        # strftime-style `+FORMAT` support. Not captured from a live device
        # in this environment (none was available); same caveat as
        # ip_addr_show_result above.
        self._device_timestamp_result = device_timestamp_result or CommandResult(
            stdout="2026-08-26T18:23:45\n", stderr="", exit_code=0, duration_ms=15.0
        )
        self._device_utc_offset_result = device_utc_offset_result or CommandResult(
            stdout="+0000\n", stderr="", exit_code=0, duration_ms=15.0
        )

    def _raise_if_unavailable(self) -> None:
        if self._unavailable:
            raise AdbUnavailableError(
                "Could not find or execute the adb binary (simulated).",
                details={"adb_path": "adb"},
                remediation="Install Android platform-tools and ensure 'adb' is on PATH.",
            )

    async def list_devices(self) -> list[DeviceInfo]:
        self._raise_if_unavailable()
        return list(self._devices)

    async def version(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._version_result

    async def wait_for_device(
        self, serial: str, wait_token: str, timeout_s: float
    ) -> CommandResult:
        self._raise_if_unavailable()
        if self._wait_for_device_timeout:
            raise AdbTimeoutError(
                f"adb command timed out after {timeout_s * 1000:.0f}ms.",
                details={"timeout_ms": timeout_s * 1000, "command": f"-s {serial} {wait_token}"},
                remediation="The device or adb server may be busy or unresponsive. Retrying is reasonable.",
            )
        return self._wait_for_device_result

    async def exec_out(self, serial: str, command: str) -> ExecOutResult:
        self._raise_if_unavailable()
        return self._exec_out_result

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self._raise_if_unavailable()
        if command.startswith("dumpsys user --user "):
            if self._user_info_result is not None:
                return self._user_info_result
            user_id = command.rsplit(" ", 1)[-1]
            # Real adb wording/shape for a single filtered user block.
            return CommandResult(
                stdout=(
                    f"  UserInfo{{{user_id}:Driver:412}} serialNo={user_id} isPrimary=false\n"
                    "    Type: android.os.usertype.full.SECONDARY\n"
                    "    Flags: 1042 (ADMIN|FULL|INITIALIZED)\n"
                    "    State: RUNNING_UNLOCKED\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=60.0,
            )
        if command == "dumpsys user":
            return self._dumpsys_user_result
        if command == "cmd user list -v":
            return self._list_users_result
        if command.startswith("am switch-user "):
            return self._switch_user_result
        if command.startswith("am start-user "):
            return self._start_user_result
        if command.startswith("am is-user-stopped "):
            return self._is_user_stopped_result
        if command.startswith("am get-started-user-state "):
            return self._user_state_result
        if command.startswith("am instrument "):
            return self._instrument_result
        if command.startswith("content query "):
            return self._content_query_result
        if command.startswith("pm create-user "):
            return self._create_user_result
        if command.startswith("pm remove-user "):
            return self._remove_user_result
        if command == "pm supports-multiple-users":
            return self._supports_multiple_users_result
        if command == "pm get-max-users":
            return self._max_users_result
        if command == "pm get-max-running-users":
            return self._max_running_users_result
        if command == "cmd user is-headless-system-user-mode":
            return self._headless_system_user_mode_result
        if command == "cmd user is-visible-background-users-supported":
            return self._visible_background_users_supported_result
        if command == "cmd user is-visible-background-users-on-default-display-supported":
            return self._visible_background_users_on_default_display_supported_result
        if command.startswith("logcat -d -t 1 -b ") and command.endswith("-v epoch"):
            return self._log_session_anchor_result
        if command.startswith("logcat -d -v threadtime -b "):
            return self._log_session_stop_result
        if command.startswith("logcat -d ") and "--pid=" in command:
            return self._package_logs_result
        if command.startswith("logcat -d "):
            return self._read_logs_result
        if command.startswith("logcat -c "):
            return self._clear_logs_result
        if command.startswith("logcat -g "):
            return self._get_log_buffer_size_result
        if command.startswith("pidof -s "):
            return self._pidof_result
        if command.startswith("pidof "):
            return self._pidof_names_result
        if command.startswith("ps -A"):
            return self._ps_result
        if command == "getprop":
            return self._list_properties_result
        if command.startswith("getprop -Z "):
            return self._getprop_context_result
        if command.startswith("getprop "):
            return self._getprop_result
        if command.startswith("setprop "):
            return self._setprop_result
        if command.startswith("pm list packages"):
            return self._list_packages_result
        if command.startswith("pm path"):
            return self._pm_path_result
        if command.startswith("dumpsys package "):
            return self._dumpsys_package_result
        if command.startswith(
            ("pm enable ", "pm disable ", "pm disable-user ", "pm default-state ", "pm default ")
        ):
            if self._pm_set_enabled_result is not None:
                return self._pm_set_enabled_result
            return _synthesize_pm_set_enabled(command)
        if command.startswith("pm uninstall"):
            return self._pm_uninstall_result
        if command.startswith("pm install-existing --user "):
            if self._pm_install_existing_result is not None:
                return self._pm_install_existing_result
            rest = command[len("pm install-existing --user ") :]
            user_id_str, _, package = rest.partition(" ")
            return CommandResult(
                stdout=f"Package {package} installed for user: {user_id_str}\n",
                stderr="",
                exit_code=0,
                duration_ms=300.0,
            )
        if command.startswith("pm clear --cache-only "):
            if self._pm_clear_cache_timeout:
                raise AdbTimeoutError(
                    "adb command timed out (simulated).",
                    details={"command": command},
                    remediation="Retrying is reasonable.",
                )
            return self._pm_clear_cache_result
        if command.startswith("rm -rf ") and "/cache" in command:
            return self._rm_cache_result
        if command.startswith("pm clear "):
            return self._clear_app_data_result
        if command.startswith("am broadcast "):
            return self._send_broadcast_result
        if command.startswith("am start-service "):
            return self._start_service_result
        if command.startswith("am start-foreground-service "):
            return self._start_foreground_service_result
        if command.startswith("am stop-service "):
            return self._stop_service_result
        if command.startswith("dumpsys activity services "):
            return self._dumpsys_activity_services_result
        if command.startswith("cmd package resolve-activity"):
            return self._resolve_activity_result
        if command == "dumpsys activity activities":
            return self._dumpsys_activity_activities_result
        if command.startswith("am start "):
            return self._start_activity_result
        if command.startswith("am force-stop "):
            return self._force_stop_result
        if command.startswith("am kill "):
            return self._am_kill_result
        if command.startswith("input ") and " tap " in command:
            return self._input_tap_result
        if command.startswith("input ") and " swipe " in command:
            return self._input_swipe_result
        if command.startswith("input ") and " text " in command:
            return self._input_text_result
        if command.startswith("input ") and " keyevent " in command:
            return self._input_keyevent_result
        if command.startswith("uiautomator dump "):
            return self._uiautomator_dump_result
        if command.startswith("cat ") and "adb_automation_mcp_ui_dump_" in command:
            return self._ui_hierarchy_cat_result
        if command.startswith("pm grant "):
            return self._grant_permission_result
        if command.startswith("pm revoke "):
            return self._revoke_permission_result
        if command.startswith("settings ") and " put " in command:
            tokens = shlex.split(command)
            idx = tokens.index("put")
            namespace, key, value = tokens[idx + 1], tokens[idx + 2], tokens[idx + 3]
            if self._set_setting_result.exit_code == 0:
                self._settings_store[f"{namespace}/{key}"] = value
            return self._set_setting_result
        if command.startswith("settings ") and " get " in command:
            tokens = shlex.split(command)
            idx = tokens.index("get")
            namespace, key = tokens[idx + 1], tokens[idx + 2]
            stored = self._settings_store.get(f"{namespace}/{key}")
            if stored is not None:
                return CommandResult(
                    stdout=f"{stored}\n", stderr="", exit_code=0, duration_ms=15.0
                )
            return self._get_setting_result
        if command.startswith("screenrecord "):
            return self._screenrecord_result
        if command == "dumpsys display":
            return self._dumpsys_display_result
        if command.startswith("wm size"):
            return self._wm_size_result
        if command.startswith("wm density"):
            return self._wm_density_result
        if command.startswith("dumpsys meminfo "):
            return self._dumpsys_meminfo_result
        if command.startswith("dumpsys dropbox --print system_app_anr"):
            return self._dropbox_system_anr_result
        if command.startswith("dumpsys dropbox"):
            return self._dropbox_print_result
        if command == "dumpsys power":
            return self._dumpsys_power_result
        if command == "dumpsys connectivity":
            return self._dumpsys_connectivity_result
        if command == "ip addr show":
            return self._ip_addr_show_result
        if command == "ip route":
            return self._ip_route_result
        if command == "date +%Y-%m-%dT%H:%M:%S":
            return self._device_timestamp_result
        if command == "date +%z":
            return self._device_utc_offset_result
        return self._shell_result

    async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult:
        self._raise_if_unavailable()
        return self._install_result

    async def uninstall(self, serial: str, package: str, keep_data: bool) -> CommandResult:
        raise NotImplementedError("FakeBackend.uninstall: no module needs this yet")

    async def push(self, serial: str, local_path: str, remote_path: str) -> CommandResult:
        self._raise_if_unavailable()
        return self._push_result

    async def forward(
        self, serial: str, local: str, remote: str, no_rebind: bool
    ) -> CommandResult:
        self._raise_if_unavailable()
        if self._forward_result is not None:
            return self._forward_result
        return _echo_resolved_tcp_port(local)

    async def forward_list(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._forward_list_result

    async def forward_remove(self, serial: str, local: str) -> CommandResult:
        self._raise_if_unavailable()
        return self._forward_remove_result

    async def reverse(
        self, serial: str, remote: str, local: str, no_rebind: bool
    ) -> CommandResult:
        self._raise_if_unavailable()
        if self._reverse_result is not None:
            return self._reverse_result
        return _echo_resolved_tcp_port(remote)

    async def reverse_list(self, serial: str) -> CommandResult:
        self._raise_if_unavailable()
        return self._reverse_list_result

    async def reverse_remove(self, serial: str, remote: str) -> CommandResult:
        self._raise_if_unavailable()
        return self._reverse_remove_result

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
        self._raise_if_unavailable()
        if self._pull_result is not None:
            return self._pull_result
        return CommandResult(
            stdout=f"{remote_path}: 1 file pulled, 0 skipped. 4.2 MB/s (1024 bytes in 0.002s)\n",
            stderr="",
            exit_code=0,
            duration_ms=180.0,
        )

    async def kill_server(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._kill_server_result

    async def start_server(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._start_server_result

    async def connect(self, host: str, port: int) -> CommandResult:
        self._raise_if_unavailable()
        if self._connect_result is not None:
            return self._connect_result
        # Real adb wording (AOSP adb_client.cpp) for a fresh successful connect.
        return CommandResult(
            stdout=f"connected to {host}:{port}\n", stderr="", exit_code=0, duration_ms=220.0
        )

    async def disconnect(self, host: str, port: int) -> CommandResult:
        self._raise_if_unavailable()
        if self._disconnect_result is not None:
            return self._disconnect_result
        return CommandResult(
            stdout=f"disconnected {host}:{port}\n", stderr="", exit_code=0, duration_ms=15.0
        )

    async def root(self, serial: str) -> CommandResult:
        self._raise_if_unavailable()
        return self._root_result

    async def unroot(self, serial: str) -> CommandResult:
        self._raise_if_unavailable()
        return self._unroot_result

    async def reboot(self, serial: str, mode: str | None = None) -> CommandResult:
        self._raise_if_unavailable()
        return self._reboot_result
