Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
AppPath = FSO.BuildPath(ScriptDir, "app\JRC_Local_Server_Health.pyw")
WshShell.Run "pythonw.exe """ & AppPath & """", 1, False
