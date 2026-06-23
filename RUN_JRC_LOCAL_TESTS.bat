@echo off
setlocal
cd /d "%~dp0"
echo ================================================================
echo J and R Construction Manager - Local Test Runner
echo ================================================================
echo.

set PYEXE=
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if not defined PYEXE set "PYEXE=py -3"

echo Using Python: %PYEXE%
echo.

echo [1/4] Installing requirements if needed...
%PYEXE% -m pip install --upgrade pip
if exist requirements.txt %PYEXE% -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo.
echo [2/4] Compiling app files...
%PYEXE% -m compileall app sitecustomize.py tests
if errorlevel 1 goto fail

echo.
echo [3/4] Running smoke tests...
%PYEXE% -m unittest discover -s tests -p "test_*.py" -v
if errorlevel 1 goto fail

echo.
echo [4/4] Running host quick test...
%PYEXE% -m app.host_quick_test
if errorlevel 1 goto warn

echo.
echo ================================================================
echo JRC LOCAL TESTS PASSED
echo ================================================================
pause
exit /b 0

:warn
echo.
echo ================================================================
echo Core tests passed, but host quick test needs attention.
echo Check exports\JRC_Host_Quick_Test_*.json and logs\shared_host_last.log.
echo ================================================================
pause
exit /b 2

:fail
echo.
echo ================================================================
echo JRC LOCAL TESTS FAILED
echo Check the error above and send the log/output to ChatGPT.
echo ================================================================
pause
exit /b 1
