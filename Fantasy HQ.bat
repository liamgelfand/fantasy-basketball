@echo off
rem Double-click to open Fantasy HQ in your browser.
cd /d "%~dp0"
if not exist "web\dist\index.html" (
  echo Building the web app for the first time...
  pushd web
  call npm install || goto :error
  call npm run build || goto :error
  popd
)
".venv\Scripts\python.exe" -m fbb serve
goto :eof

:error
echo Build failed. Make sure Node.js 20+ is installed.
pause
