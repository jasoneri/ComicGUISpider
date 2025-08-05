#!/bin/bash
# 将终端窗口置于最前
osascript -e 'tell application "Terminal" to activate' -e 'tell application "System Events" to tell process "Terminal" to set frontmost to true'

# 检测是否为 Apple Silicon
if [ "$(uname -m)" = "arm64" ]; then
    BREW_PATH="/opt/homebrew/bin/brew"
else
    BREW_PATH="/usr/local/bin/brew"
fi

# 如果没有安装 Homebrew，则安装它
if [ ! -x "$BREW_PATH" ]; then
    echo "[CGS]installing Homebrew..."
    /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
fi

# 安装 uv（如果尚未安装）
if ! command -v uv &> /dev/null; then
    echo "[CGS]installing uv..."
    "$BREW_PATH" install uv
fi

locale=$(defaults read -g AppleLocale)
if [[ "$locale" == "zh_CN"* ]]; then
    INDEX_URL="--index-url https://pypi.tuna.tsinghua.edu.cn/simple"
else
    INDEX_URL=""
fi

uv tool install ComicGUISpider --force $INDEX_URL

uv tool update-shell

echo "5s后将自动关闭终端窗口, 请新开终端手动重启cgs/重开 CGS.app ..."
echo "Terminal will close in 5s, please open new terminal to run cgs/reopen CGS.app ..."
sleep 5
exit 0
