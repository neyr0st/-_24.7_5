@echo off
cd /d "%~dp0"

set PY="C:\Users\neyr0st\AppData\Local\Python\pythoncore-3.14-64\python.exe"

echo Using Python: %PY%
%PY% --version
if errorlevel 1 goto :fail

echo Installing PyInstaller...
%PY% -m pip install pyinstaller
if errorlevel 1 goto :fail

echo Building...
%PY% -m PyInstaller --onefile --name QRGenerator launcher.py
if errorlevel 1 goto :fail

if exist dist\QRGenerator.exe (
    echo SUCCESS: dist\QRGenerator.exe
) else (
    echo FAILED: dist\QRGenerator.exe not found
)
goto :end

:fail
echo BUILD FAILED. See messages above.

:end
pause