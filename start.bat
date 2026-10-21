@echo off
cd /d %~dp0
where pythonw >nul 2>nul && (start "" pythonw desktop_pet.py) || (start "" pyw desktop_pet.py)
