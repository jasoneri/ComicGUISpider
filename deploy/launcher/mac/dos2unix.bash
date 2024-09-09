#!/bin/bash
curr_p=$(cd "$(dirname "$0")";pwd)
app_proj_p="/Applications/CGS.app/Contents/Resources/scripts"
if [ ! -x /usr/local/bin/brew ]; then
  echo "not brew, downloading brew...";
  /bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)";
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
