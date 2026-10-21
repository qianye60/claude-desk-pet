@echo off
cd /d %~dp0
python autostart.py off || py autostart.py off
pause
