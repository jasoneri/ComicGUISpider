#!/bin/bash
# 将终端窗口置于最前
osascript -e 'tell application "Terminal" to activate' -e 'tell application "System Events" to tell process "Terminal" to set frontmost to true'

PROJ_P="/Applications/CGS.app/Contents/Resources/scripts";
cd $PROJ_P;

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

speed_gtihub() {
    ori_url=$1
    speedPrefix=""
    read -p "是否启用下载加速？(y/n) " enableSpeed
    if [[ "$enableSpeed" =~ ^[Yy]$ ]]; then
        read -p "请粘贴格式链接（进 github.akams.cn 输入任意字符获取，例如：https://aaaa.bbbb/https/114514）" speedUrl
        if [[ "$speedUrl" =~ (https?://[^/]+) ]]; then
            speedPrefix="${BASH_REMATCH[1]}"
            printf "✈️ 加速前缀: %s\n" "$speedPrefix" >&2
        else
            printf "❌ 链接格式无效，不使用加速\n" >&2
            speedPrefix=""
        fi
    fi
    echo "${speedPrefix}/$ori_url"
}

echo "[CGS]uv installing python..."
mirrorUrl=$(speed_gtihub "https://github.com/astral-sh/python-build-standalone/releases/download")

# 检查是否已安装 Python 3.12.11
if ! uv python list | grep "3.12.11"; then
    uv python install 3.12.11 --mirror "$mirrorUrl" --no-cache
fi

cd "/Applications/CGS.app/Contents/Resources/scripts";
echo "[CGS]Installing dependencies using pyproject.toml..."
uv sync --index-url https://repo.huaweicloud.com/repository/pypi/simple

echo ""
echo "===== 初始化/依赖更新完毕，现可在启动台启动 CGS 了 ====="
echo ""
