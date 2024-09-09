#!/bin/bash
curr_p=$(cd "$(dirname "$0")";pwd);
cd $curr_p/../../../;

if [ ! -x /usr/local/bin/python3.12 ];
    then echo "无python3.12环境，正在初始化...";
    if [ ! -x /usr/local/bin/brew ]; then
      echo "not brew, downloading brew...";
      /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
    fi
    brew install python@3.12;
    brew link python@3.12;
fi

/usr/local/bin/python3.12 deploy/__init__.py;
/usr/local/bin/python3.12 -m pip install -r requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --user --break-system-packages;

echo ""
echo "===== 初始化完毕，请手动关闭终端窗口 ====="
echo ""