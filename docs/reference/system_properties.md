# system_properties

Android system properties on a connected device — read, list (optionally by prefix),
inspect metadata (SELinux context/declared type), and set ordinary mutable ones.
Control-property namespaces (`ctl.*`, `sys.powerctl`) are refused, since they
represent lifecycle/power operations rather than plain property mutation.

::: adb_automation_mcp.modules.system_properties.tools
