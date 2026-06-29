Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
Base = FSO.GetParentFolderName(WScript.ScriptFullName)
Pyw = Base & "\.venv\Scripts\pythonw.exe"
Py = Base & "\.venv\Scripts\python.exe"
Script = Base & "\app\live_full_update.py"
Cmd = ""
If FSO.FileExists(Pyw) Then
  Cmd = Chr(34) & Pyw & Chr(34) & " " & Chr(34) & Script & Chr(34)
ElseIf FSO.FileExists(Py) Then
  Cmd = Chr(34) & Py & Chr(34) & " " & Chr(34) & Script & Chr(34)
Else
  Cmd = "py -3 " & Chr(34) & Script & Chr(34)
End If
WshShell.CurrentDirectory = Base
WshShell.Run Cmd, 0, True
