#!/bin/bash
curr_p=$(cd "$(dirname "$0")";pwd);
cd $curr_p/../../../;

# 检测系统架构
if [ "$(uname -m)" = "arm64" ]; then
    PYTHON_PATH="/opt/homebrew/bin/python3.12"
    BREW_PATH="/opt/homebrew/bin/brew"
else
    PYTHON_PATH="/usr/local/bin/python3.12"
    BREW_PATH="/usr/local/bin/brew"
fi

if [ ! -x "$PYTHON_PATH" ]; then
    echo "无python3.12环境，正在初始化...";
    if [ ! -x "$BREW_PATH" ]; then
        echo "not brew, downloading brew...";
        /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
    fi
    "$BREW_PATH" install python@3.12;
    "$BREW_PATH" link python@3.12;
fi

"$PYTHON_PATH" deploy/__init__.py;
echo "正在安装依赖（自动过滤macOS不兼容包）..."
cat requirements.txt | grep -vE 'pywin32==|twisted-iocpsupport==' | "$PYTHON_PATH" -m pip install -r /dev/stdin \
    -i http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --user \
    --break-system-packages;

echo ""
echo "===== 初始化完毕，请手动关闭终端窗口 ====="
echo ""