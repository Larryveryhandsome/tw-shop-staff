' Start staff system + shareholder site, then open the browser
' Runs Python hidden (no console window). Requires Python 3.11+ (python.org installer adds pythonw / pyw).
Option Explicit
Dim sh, fso, here, cmd, exe, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
On Error Resume Next
For Each exe In Array("pythonw", "pyw")
  Err.Clear
  rc = sh.Run(exe & " -X utf8 ""tools\launcher.py"" start --open", 0, False)
  If Err.Number = 0 Then WScript.Quit 0
Next
MsgBox "Python 3.11+ not found. Please install it from https://www.python.org/downloads/ (check 'Add python.exe to PATH').", 48, "shop-staff"
