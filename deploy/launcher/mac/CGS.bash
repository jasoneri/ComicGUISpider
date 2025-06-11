#!/bin/bash
cd /Applications/CGS.app/Contents/Resources;

# 检测是否为 Apple Silicon
if [ "$(uname -m)" = "arm64" ]; then
    PYTHON_PATH="/opt/homebrew/bin/python3.12"
else
    PYTHON_PATH="/usr/local/bin/python3.12"
fi

source .venv/bin/activate
cd scripts;
python CGS.py;
deactivate
