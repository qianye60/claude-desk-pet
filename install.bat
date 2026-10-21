@echo off
cd /d %~dp0
echo Installing PySide6 and Pillow...
python -m pip install -r requirements.txt || py -m pip install -r requirements.txt
echo.
echo Done. Double-click start.bat to launch the pet.
pause
