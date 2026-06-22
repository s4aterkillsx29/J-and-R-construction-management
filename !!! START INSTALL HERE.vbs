Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
target = base & "\INSTALL_J_AND_R_MANAGER.vbs"
If fso.FileExists(target) Then
    shell.Run Chr(34) & target & Chr(34), 1, False
Else
    MsgBox "INSTALL_J_AND_R_MANAGER.vbs not found in this folder.", 48, "J and R Construction Manager"
End If
