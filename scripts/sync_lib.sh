#!/bin/sh
# Копіює бібліотеку в app/src, щоб `flet build apk` упакував її разом із застосунком.
set -e
cd "$(dirname "$0")/.."
rm -rf app/src/nzua
cp -r src/nzua app/src/nzua
find app/src/nzua -name __pycache__ -type d -exec rm -rf {} +
echo "nzua -> app/src/nzua"
