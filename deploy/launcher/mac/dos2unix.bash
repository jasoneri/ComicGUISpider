#!/bin/bash
curr_p=$(cd "$(dirname "$0")";pwd)
app_proj_p="/Applications/CGS.app/Contents/Resources/scripts"
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
find $curr_p/../ -type f -name "*.bash" -exec sudo dos2unix {} +;
find $curr_p/../ -type f -name "*.md" -exec sudo dos2unix {} +;
find $curr_p/../ -type f -name "*.py" -exec sudo dos2unix {} +;
find $curr_p/../ -type f -name "*.json" -exec sudo dos2unix {} +;
find $curr_p/../ -type f -name "*.yml" -exec sudo dos2unix {} +;
find $app_proj_p -type f -name "*.bash" -exec sudo dos2unix {} +;
find $app_proj_p -type f -name "*.md" -exec sudo dos2unix {} +;
find $app_proj_p -type f -name "*.py" -exec sudo dos2unix {} +;
find $app_proj_p -type f -name "*.json" -exec sudo dos2unix {} +;
find $app_proj_p -type f -name "*.yml" -exec sudo dos2unix {} +;
