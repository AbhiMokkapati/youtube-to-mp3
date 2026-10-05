Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = "C:\Python314\pythonw.exe"
gui = """" & scriptDir & "\yt2mp3_gui.py" & """"
logPath = scriptDir & "\launch_error.log"

' A previous launch's log may still be open if that instance is still
' running (or was force-closed) — deleting it is a courtesy, not required,
' so any failure here is ignored rather than shown as an error dialog.
On Error Resume Next
If fso.FileExists(logPath) Then fso.DeleteFile logPath
On Error Goto 0

' NOTE: pythonExe must stay unquoted here (it has no spaces) — cmd.exe's
' "/c" parsing mis-handles a command that starts with a quoted token
' followed by redirection, throwing "filename...syntax is incorrect".
cmd = "cmd /c " & pythonExe & " " & gui & " 1>""" & logPath & """ 2>&1"
shell.Run cmd, 0, False

' pythonw has no console, so a startup crash would otherwise be silent.
' Give it a couple seconds, then surface any error that was logged.
' (If the app is still running, the log stays open at size 0 — that's
' fine, it just gets cleaned up on the next launch, above.)
WScript.Sleep 2500
If fso.FileExists(logPath) Then
    Set f = fso.GetFile(logPath)
    If f.Size > 0 Then
        shell.Run "notepad.exe """ & logPath & """", 1, False
    End If
End If
