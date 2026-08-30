# packages

Installed-app management on a connected device: listing (`adb shell pm list
packages`), installing (`adb install`), uninstalling (`adb shell pm
uninstall`), and making an already-installed package available to another
Android user (`adb shell pm install-existing`). Exposes semantic install/
uninstall options rather than raw adb/pm flags — see install_apk's Args for
how each option maps to Android's supported installation behavior. Split
APK/APK-bundle/APEX installation, staged installs/install sessions,
install-location management, and package enable/disable/suspend aren't
implemented yet.

::: adb_automation_mcp.modules.packages.tools
