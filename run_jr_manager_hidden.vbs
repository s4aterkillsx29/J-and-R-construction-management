Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
Base = FSO.GetParentFolderName(WScript.ScriptFullName)
EnsurePs1 = Base & "\scripts\Ensure-DesktopShortcuts.ps1"
EnsureBat = Base & "\ensure_venv.bat"
If FSO.FileExists(EnsureBat) Then
  WshShell.CurrentDirectory = Base
  WshShell.Run "cmd.exe /c """ & EnsureBat & """ >nul 2>&1", 0, True
End If
If FSO.FileExists(EnsurePs1) Then
  WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & EnsurePs1 & Chr(34) & " -InstallDir " & Chr(34) & Base & Chr(34) & " -Quiet", 0, False
End If
Pyw = Base & "\.venv\Scripts\pythonw.exe"
Py = Base & "\.venv\Scripts\python.exe"
ModuleArgs = "-m app.program_shell"
If FSO.FileExists(Pyw) Then
  WshShell.CurrentDirectory = Base
  WshShell.Run Chr(34) & Pyw & Chr(34) & " " & ModuleArgs, 0, False
ElseIf FSO.FileExists(Py) Then
  WshShell.CurrentDirectory = Base
  WshShell.Run Chr(34) & Py & Chr(34) & " " & ModuleArgs, 0, False
Else
  WshShell.Run "pyw -3 " & ModuleArgs, 0, False
End If
