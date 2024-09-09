#!/bin/bash
curr_p=$(cd "$(dirname "$0")";pwd);
cd $curr_p/../../../;

if [ ! -x /usr/local/bin/python3.12 ];
    then echo "无python3.12环境，正在初始化...";
    if [ ! -x /usr/local/bin/brew ]; then
      echo "not brew, downloading brew...";
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)";
      git -C "$(brew --repo)" remote set-url origin https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/brew.git;
      git -C "$(brew --repo homebrew/core)" remote set-url origin https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-core.git;
      git -C "$(brew --repo homebrew/cask)" remote set-url origin https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-cask.git;
      git -C "$(brew --repo homebrew/cask-fonts)" remote set-url origin https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-cask-fonts.git;
      git -C "$(brew --repo homebrew/cask-drivers)" remote set-url origin https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-cask-drivers.git;
      brew update
    fi
    brew install python@3.12;
    brew link python@3.12;
fi

/usr/local/bin/python3.12 deploy/__init__.py;
/usr/local/bin/python3.12 -m pip install -r requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --user --break-system-packages;

echo ""
echo "===== 初始化完毕，点击quit退出 ====="
echo ""