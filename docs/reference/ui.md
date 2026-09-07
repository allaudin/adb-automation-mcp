# ui

Retrieving the current Android UI hierarchy (`uiautomator dump`) as inline
XML, and searching it by structured criteria (`find_ui_elements`,
`wait_for_ui_element`) — no temporary device-file location for the caller to
know or manage, no XML parsing on the caller's side. Input actions aren't
implemented here (see the input module for touch injection).

::: adb_automation_mcp.modules.ui.tools
