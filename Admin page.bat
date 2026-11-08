@echo off
rem The data admin page: http://127.0.0.1:8770. Keep this window open while you use the page; close it to stop.
cd /d "%~dp0"
title Tumrah data admin page
rem open the browser only once the server answers (it takes a second or two to start)
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){try{(New-Object Net.Sockets.TcpClient('127.0.0.1',8770)).Close();break}catch{Start-Sleep -Milliseconds 500}}; Start-Process 'http://127.0.0.1:8770'"
py dm.py page
echo.
echo The admin page stopped. Read the message above, then press a key to close.
pause >nul
