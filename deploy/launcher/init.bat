@rem
@echo off

set "_root=%~dp0"
set "_root=%_root:~0,-1%"
cd "%_root%"
@echo "%_root%

set "_pyBin=%_root%\runtime"
set "PATH=%_root%\site-packages;%_pyBin%;%PATH%"

for /F "tokens=*" %%p in (scripts\requirements\win.txt) do (
    python -m pip install "%%p" || echo installed %%p failed, continue...
)
pause
