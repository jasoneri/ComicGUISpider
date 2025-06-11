#!/bin/bash
# 将终端窗口置于最前
osascript -e 'tell application "Terminal" to activate' -e 'tell application "System Events" to tell process "Terminal" to set frontmost to true'

PROJ_P="/Applications/CGS.app/Contents/Resources/scripts";
cd $PROJ_P;

# 检测是否为 Apple Silicon
if [ "$(uname -m)" = "arm64" ]; then
    REQUIREMENTS="$PROJ_P/requirements/mac_arm64.txt"
    PYTHON_PATH="/opt/homebrew/bin/python3.12"
    BREW_PATH="/opt/homebrew/bin/brew"
else
    REQUIREMENTS="$PROJ_P/requirements/mac_x86_64.txt"
    PYTHON_PATH="/usr/local/bin/python3.12"
    BREW_PATH="/usr/local/bin/brew"
fi

# 确保安装 Python
if [ ! -x "$PYTHON_PATH" ]; then
    echo "无python3.12环境，正在初始化...";
    
    # 如果没有安装 Homebrew，则安装它
    if [ ! -x "$BREW_PATH" ]; then
        echo "installing Homebrew..."
        /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
    fi
    
    # 安装 Python
    echo "installing Python 3.12..."
    "$BREW_PATH" install python@3.12
    "$BREW_PATH" link python@3.12
fi


"$PYTHON_PATH" -m pip install uv -i https://repo.huaweicloud.com/repository/pypi/simple
echo "uv installing $REQUIREMENTS..."
"$PYTHON_PATH" -m uv pip install "$REQUIREMENTS" --index-url https://repo.huaweicloud.com/repository/pypi/simple

echo ""
echo "===== 初始化/依赖更新完毕，请手动关闭终端窗口 ====="
echo ""
