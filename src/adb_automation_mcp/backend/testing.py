"""A deterministic, in-memory AdbBackend implementation for tests.

Fixture values passed in must be realistic once methods beyond list_devices are
implemented — a test is only a trustworthy predictor of real behavior if it's
exercised against real-shaped data. For now the unimplemented methods raise
NotImplementedError loudly rather than returning silently-wrong fake data.
"""

from __future__ import annotations

import base64

from adb_automation_mcp.backend.protocol import CommandResult, DeviceInfo, ExecOutResult
from adb_automation_mcp.errors import AdbUnavailableError

# A real, minimal 2x2 RGBA PNG (77 bytes) — the deterministic stand-in for
# `adb exec-out screencap -p` output. Generated once with Python's zlib/struct
# PNG encoder (a genuine, decodable PNG with a valid IHDR/IDAT/IEND), not
# hand-invented byte soup, so tests that parse its dimensions get real answers.
_FAKE_SCREENCAP_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP4z8DwHwyBNBAw/AcAR8oI+FuapL4AAAAASUVORK5CYII="
)


class FakeBackend:
    """AdbBackend implementation backed by in-memory fixtures instead of a real
    device or adb install — deterministic, fast, and usable in any environment.
    """

    def __init__(
        self,
        devices: list[DeviceInfo] | None = None,
        unavailable: bool = False,
        kill_server_result: CommandResult | None = None,
        start_server_result: CommandResult | None = None,
        connect_result: CommandResult | None = None,
        disconnect_result: CommandResult | None = None,
        root_result: CommandResult | None = None,
        shell_result: CommandResult | None = None,
        dumpsys_user_result: CommandResult | None = None,
        user_info_result: CommandResult | None = None,
        list_users_result: CommandResult | None = None,
        switch_user_result: CommandResult | None = None,
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
        install_result: CommandResult | None = None,
        pm_uninstall_result: CommandResult | None = None,
        pm_install_existing_result: CommandResult | None = None,
        send_broadcast_result: CommandResult | None = None,
        start_activity_result: CommandResult | None = None,
        start_service_result: CommandResult | None = None,
        force_stop_result: CommandResult | None = None,
        pull_result: CommandResult | None = None,
        clear_app_data_result: CommandResult | None = None,
        exec_out_result: ExecOutResult | None = None,
        input_tap_result: CommandResult | None = None,
        uiautomator_dump_result: CommandResult | None = None,
        ui_hierarchy_cat_result: CommandResult | None = None,
        grant_permission_result: CommandResult | None = None,
        get_setting_result: CommandResult | None = None,
        dumpsys_power_result: CommandResult | None = None,
        ip_addr_show_result: CommandResult | None = None,
        device_timestamp_result: CommandResult | None = None,
        device_utc_offset_result: CommandResult | None = None,
    ) -> None:
        self._devices = devices or []
        self._unavailable = unavailable
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
        # `adb shell am force-stop` — the well-documented, long-stable AOSP
        # behavior: no stdout at all on success. Not captured from a live
        # device in this environment (none was available); same caveat as
        # start_service_result above.
        self._force_stop_result = force_stop_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=90.0
        )
        # None (the default) means "build a realistic success message from
        # whatever remote_path is actually pulled" — see pull() below, same
        # convention as connect_result. Real, long-stable `adb pull` wording.
        self._pull_result = pull_result
        # `adb shell pm clear` — PackageManagerShellCommand's documented,
        # long-stable success text: a bare "Success". Not captured from a
        # live device in this environment (none was available); same caveat
        # as force_stop_result above.
        self._clear_app_data_result = clear_app_data_result or CommandResult(
            stdout="Success\n", stderr="", exit_code=0, duration_ms=110.0
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
        # `settings get NAMESPACE KEY` — a typical set value. Not captured
        # from a live device in this environment (none was available); same
        # caveat as grant_permission_result above.
        self._get_setting_result = get_setting_result or CommandResult(
            stdout="128\n", stderr="", exit_code=0, duration_ms=40.0
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

    async def exec_out(self, serial: str, command: str) -> ExecOutResult:
        self._raise_if_unavailable()
        return self._exec_out_result

    async def shell(self, serial: str, command: str) -> CommandResult:
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
        if command.startswith("pm clear "):
            return self._clear_app_data_result
        if command.startswith("am broadcast "):
            return self._send_broadcast_result
        if command.startswith("am start-service "):
            return self._start_service_result
        if command.startswith("am start "):
            return self._start_activity_result
        if command.startswith("am force-stop "):
            return self._force_stop_result
        if command.startswith("input ") and " tap " in command:
            return self._input_tap_result
        if command.startswith("uiautomator dump "):
            return self._uiautomator_dump_result
        if command.startswith("cat ") and "adb_automation_mcp_ui_dump_" in command:
            return self._ui_hierarchy_cat_result
        if command.startswith("pm grant "):
            return self._grant_permission_result
        if command.startswith("settings ") and " get " in command:
            return self._get_setting_result
        if command == "dumpsys power":
            return self._dumpsys_power_result
        if command == "ip addr show":
            return self._ip_addr_show_result
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
        raise NotImplementedError("FakeBackend.push: no module needs this yet")

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
