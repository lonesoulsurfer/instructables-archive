#!/usr/bin/env bash
cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed."
    echo "Download it from https://python.org and try again."
    exit 1
fi

python3 run.py
echo
read -p "Press Enter to close..."
