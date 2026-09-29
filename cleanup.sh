#!/bin/bash
# Removes this entire experiment. Nothing was installed outside this folder.
DIR="$(cd "$(dirname "$0")" && pwd)"
read -p "Delete $DIR (models + outputs, ~10GB)? [y/N] " a
[ "$a" = y ] && rm -rf "$DIR" && echo "Removed. No other traces."
