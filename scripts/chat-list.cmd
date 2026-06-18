@echo off
setlocal
rem chat-list (Windows) launcher: find a working Python, run the core script with all args.
rem Robust against the pyenv-win shim erroring in a dir whose .python-version points at an
rem uninstalled version (bare 'python' then fails even though a usable Python exists).
set "SCRIPT=%~dp0chat-list.py"

rem 1) py launcher (cwd-insensitive, most reliable when present)
where py >nul 2>nul && ( py -3 "%SCRIPT%" %* & exit /b )

rem 2) currently-active virtualenv
if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" ( "%VIRTUAL_ENV%\Scripts\python.exe" "%SCRIPT%" %* & exit /b )

rem 3) python / python3 on PATH, but only if they actually execute here
rem    (the pyenv-win shim errors when the selected version is not installed)
for %%P in (python.exe python3.exe) do where %%P >nul 2>nul && %%P -c "pass" >nul 2>nul && ( %%P "%SCRIPT%" %* & exit /b )

rem 4) fall back to a venv under %USERPROFILE%\.venvs (this user's convention)
if exist "%USERPROFILE%\.venvs\" for /f "delims=" %%V in ('dir /b /ad "%USERPROFILE%\.venvs" 2^>nul') do if exist "%USERPROFILE%\.venvs\%%V\Scripts\python.exe" ( "%USERPROFILE%\.venvs\%%V\Scripts\python.exe" "%SCRIPT%" %* & exit /b )

rem 5) pyenv-win: call an installed version directly (bypasses the shim)
set "PYENV_VERS=%USERPROFILE%\.pyenv\pyenv-win\versions"
if defined PYENV set "PYENV_VERS=%PYENV%\versions"
if exist "%PYENV_VERS%\" for /f "delims=" %%D in ('dir /b /ad /o-n "%PYENV_VERS%" 2^>nul') do if exist "%PYENV_VERS%\%%D\python.exe" ( "%PYENV_VERS%\%%D\python.exe" "%SCRIPT%" %* & exit /b )

>&2 echo chat-list: usable Python not found. Activate your venv or install Python (py launcher / pyenv).
exit /b 9
