
Dim folder
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

Set WShell = CreateObject("WScript.Shell")
WShell.CurrentDirectory = folder
' Run start.bat with no window (0 = hidden), don't wait for it to finish
WShell.Run "cmd /c start.bat >> logs\service.log 2>&1", 0, False
