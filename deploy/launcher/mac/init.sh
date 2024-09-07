sudo installer -pkg extra/python-3.12.3.pkg -target /
/usr/local/bin/python3 scripts/deploy/__init__.py
sudo /usr/local/bin/python3 -m pip install -r scripts/requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com


