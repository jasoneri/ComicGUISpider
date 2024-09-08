#!/bin/bash
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
if [ ! -x /usr/local/bin/dos2unix ]; then
  echo "not dos2unix, downloading dos2unix...";
  brew install dos2unix;
fi
find ../ -type f -name "*.bash" -exec sudo dos2unix {} +;
find ../CGS.app/Contents/Resources/scripts -type f -name "*.md" -exec sudo dos2unix {} +;
find ../CGS.app/Contents/Resources/scripts -type f -name "*.py" -exec sudo dos2unix {} +;
find ../CGS.app/Contents/Resources/scripts -type f -name "*.json" -exec sudo dos2unix {} +;
find ../CGS.app/Contents/Resources/scripts -type f -name "*.yml" -exec sudo dos2unix {} +;
