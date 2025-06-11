#!/bin/bash
cd /Applications/CGS.app/Contents/Resources;

source .venv/bin/activate
cd scripts;
python CGS.py;
deactivate
