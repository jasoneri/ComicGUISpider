#!/bin/bash
curr_p=$(cd "$(dirname "$0")";pwd);
cd $curr_p/../../../;
/usr/local/bin/python3.12 deploy/update.py;
read -p "Press any key to continue..." -t 15;