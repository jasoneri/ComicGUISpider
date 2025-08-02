#!/bin/bash
if [ ! -x "cgs" ]; then
    curl -fsSL https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/launcher/mac/init.bash | bash && cgs
else
    cgs
fi
