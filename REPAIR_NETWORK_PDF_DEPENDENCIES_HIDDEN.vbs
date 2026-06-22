Set sh=CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\REPAIR_NETWORK_PDF_DEPENDENCIES.ps1""", 1, True
