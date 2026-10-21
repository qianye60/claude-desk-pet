@echo off
cd /d %~dp0
python autostart.py on || py autostart.py on
echo Now the pet will appear whenever Claude Desktop opens.
pause
