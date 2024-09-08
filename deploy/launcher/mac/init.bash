#!/bin/bash
scripts_path="CGS.app/Contents/Resources/scripts";

if [ ! -x /usr/local/bin/python3.12 ];
    then echo "无python3.12环境，正在初始化...";
    sudo installer -pkg extra/python-3.12.3.pkg -target /;
fi

/usr/local/bin/python3.12 $scripts_path/deploy/__init__.py;
/usr/local/bin/python3.12 -m pip install -r $scripts_path/requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com;
