@echo off
set "rootdir=%~dp0"
cd /d "%rootdir%"
cd server
start /B cmd.exe /C server.exe %*