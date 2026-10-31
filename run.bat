@echo off
rem Starts the footwear bot. Double-click, or run from a Command Prompt in this folder.
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Creating the Python environment ^(first run only^)...
  python -m venv .venv || goto :error
  call .venv\Scripts\activate.bat
  python -m pip install -r requirements.txt || goto :error
) else (
  call .venv\Scripts\activate.bat
)
if not exist config\reference\lists.json python scripts\import_reference.py
python run.py
pause
exit /b 0
:error
echo Setup failed. See the message above.
pause
exit /b 1
