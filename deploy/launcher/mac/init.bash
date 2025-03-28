#!/bin/bash
# 将终端窗口置于最前
osascript -e 'tell application "Terminal" to activate' -e 'tell application "System Events" to tell process "Terminal" to set frontmost to true'

curr_p=$(cd "$(dirname "$0")";pwd);
cd $curr_p/../../../;
REQUIREMENTS="requirements/mac_x86_64.txt"

# 检测是否为 Apple Silicon
if [ "$(uname -m)" = "arm64" ]; then
    REQUIREMENTS="requirements/mac_arm64.txt"
    # 检测 Rosetta 2 是否已安装
    if ! arch -x86_64 echo > /dev/null 2>&1; then
        echo "检测到 Apple Silicon Mac，但未安装 Rosetta 2，正在安装..."
        /usr/sbin/softwareupdate --install-rosetta --agree-to-license
    fi
fi

PYTHON_PATH="/usr/local/bin/python3.12"
# 确保安装的是 x86_64 版本的 Python
if [ ! -x "$PYTHON_PATH" ]; then
    echo "无python3.12环境，正在初始化...";
    # 检测 Homebrew 安装路径
    if [ -x "/opt/homebrew/bin/brew" ]; then
        ARM_BREW_PATH="/opt/homebrew/bin/brew"
    fi
    if [ -x "/usr/local/bin/brew" ]; then
        INTEL_BREW_PATH="/usr/local/bin/brew"
    fi
    # 如果没有安装 Homebrew，则安装它
    if [ ! -x "$INTEL_BREW_PATH" ] && [ ! -x "$ARM_BREW_PATH" ]; then
        echo "未检测到 Homebrew，正在安装..."
        /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
    fi
    # 在 Apple Silicon Mac 上，通过 Rosetta 2 安装 x86_64 版的 Python
    if [ "$(uname -m)" = "arm64" ]; then
        if [ -x "$INTEL_BREW_PATH" ]; then
            echo "使用 Intel Homebrew 安装 Python..."
            "$INTEL_BREW_PATH" install python@3.12
            "$INTEL_BREW_PATH" link python@3.12
        else
            echo "通过 Rosetta 2 安装 Intel 版本的 Python..."
            arch -x86_64 /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)"
            arch -x86_64 /usr/local/bin/brew install python@3.12
            arch -x86_64 /usr/local/bin/brew link python@3.12
        fi
    else
        # 在 Intel Mac 上，直接安装
        if [ -x "$INTEL_BREW_PATH" ]; then
            "$INTEL_BREW_PATH" install python@3.12
            "$INTEL_BREW_PATH" link python@3.12
        fi
    fi
fi

"$PYTHON_PATH" deploy/__init__.py;
echo "正在安装依赖（自动过滤macOS不兼容包）..."
cat "$REQUIREMENTS" | grep -vE 'pywin32==|twisted-iocpsupport==' | "$PYTHON_PATH" -m pip install -r /dev/stdin \
    -i http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --user \
    --break-system-packages;

echo ""
echo "===== 初始化完毕，请手动关闭终端窗口 ====="
echo ""