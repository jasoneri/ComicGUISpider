@rem
@echo off
set "_root=%~dp0..\..\.."
cd /d "%_root%"

echo "%_root%"
set "PATH=%_root%\site-packages;%_pyBin%;%PATH%"
set "_uvBin=%_root%\runtime\uv.exe"

"%_uvBin%" pip install -r "%_root%\scripts\requirements\win.txt" --python "%_root%\runtime\python.exe" %*
