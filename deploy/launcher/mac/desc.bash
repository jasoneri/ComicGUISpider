#!/bin/bash
scripts_path="CGS.app/Contents/Resources/scripts";
/usr/local/bin/python3.12 $scripts_path/deploy/update.py -d;
open $scripts_path/desc.html;