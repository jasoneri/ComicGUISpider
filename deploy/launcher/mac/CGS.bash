#!/bin/bash
cd scripts;

# 检测系统架构
if [ "$(uname -m)" = "arm64" ]; then
    PYTHON_PATH="/opt/homebrew/bin/python3.12"
else
    PYTHON_PATH="/usr/local/bin/python3.12"
fi

"$PYTHON_PATH" CGS.py;