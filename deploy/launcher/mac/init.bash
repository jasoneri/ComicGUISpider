#!/bin/bash
# 将终端窗口置于最前
osascript -e 'tell application "Terminal" to activate' -e 'tell application "System Events" to tell process "Terminal" to set frontmost to true'

# 检测是否为 Apple Silicon
if [ "$(uname -m)" = "arm64" ]; then
    BREW_PATH="/opt/homebrew/bin/brew"
    BREW_BIN="/opt/homebrew/bin"
else
    BREW_PATH="/usr/local/bin/brew"
    BREW_BIN="/usr/local/bin"
fi
export PATH="$BREW_BIN:$PATH"

# 如果没有安装 Homebrew，则安装它
if [ ! -x "$BREW_PATH" ]; then
    echo "[CGS]installing Homebrew..."
    /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
fi

# 安装 uv（如果尚未安装）
if ! command -v uv &> /dev/null; then
    echo "[CGS]installing uv..."
    "$BREW_PATH" install uv
    hash -r
fi
uv tool update-shell
export PATH="$(uv tool dir --bin):$PATH"

DEFAULT_SOURCE="1"
SOURCE_OPTION=${1:-$DEFAULT_SOURCE}
INDEX_URL=""
case $SOURCE_OPTION in
    1 | "")
        INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple/"
        ;;
    2)
        INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
        ;;
    3)
        INDEX_URL="https://repo.huaweicloud.com/repository/pypi/simple/"
        ;;
    *) 
        echo "将使用pypi官方源。"
        INDEX_URL="https://pypi.org/simple"
        ;;
esac
echo "$INDEX_URL"

if ! command -v cgs &> /dev/null; then
    echo "[CGS]installing cgs..."
    uv tool install ComicGUISpider --force --index-url "$INDEX_URL"
else
    echo "→ cgs installed, now runing"
fi

cgs