#!/bin/env bash

unameOut="$(uname -s)"

case "${unameOut}" in
    Linux*)     machine="Linux";;
    Darwin*)    machine="Mac";;
    *)          machine="${unameOut}"
esac

if [ "$machine" = "Mac" ]; then
    SCR_DIR=`dirname $(readlink -f $0)`
else
    SCR_DIR=`dirname $(readlink -e -- $0)`
fi

THISDIR=`dirname $SCR_DIR`
# PICO_DEV="${1:-/dev/ttyACM0}"

# Create venv, if missing
if [ ! -d "$THISDIR/.venv" ]; then
    python3 -m venv "$THISDIR/.venv"
fi

# Activate venv
. "$THISDIR/.venv/bin/activate"
trap deactivate EXIT

# Install requirements
pip3 install \
    adafruit-circuitpython-bno08x \
    adafruit-circuitpython-dps310 \
    adafruit-circuitpython-register \
    adafruit-circuitpython-bus-device \
    adafruit-circuitpython-httpserver
echo "Done!"
