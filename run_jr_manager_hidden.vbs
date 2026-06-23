Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
Base = FSO.GetParentFolderName(WScript.ScriptFullName)
Script = Base & "\app\start_center.py"
Pyw = Base & "\.venv\Scripts\pythonw.exe"
Py = Base & "\.venv\Scripts\python.exe"
If FSO.FileExists(Pyw) Then
  WshShell.Run Chr(34) & Pyw & Chr(34) & " " & Chr(34) & Script & Chr(34), 1, False
ElseIf FSO.FileExists(Py) Then
  WshShell.Run Chr(34) & Py & Chr(34) & " " & Chr(34) & Script & Chr(34), 1, False
Else
  ' Prefer pyw/py launcher when Python is installed normally.
  WshShell.Run "pyw -3 " & Chr(34) & Script & Chr(34), 1, False
End If
