@echo off
rem chat-list (Windows) - run the cross-tool conversation history browser.
rem Put this file's directory (the library `scripts\`) on PATH, then run: chat-list ...
rem Prefer the `py` launcher; fall back to `python`. Forwards all args (%*).
where py >nul 2>nul && goto :usepy
python "%~dp0chat-list.py" %*
goto :eof
:usepy
py "%~dp0chat-list.py" %*
