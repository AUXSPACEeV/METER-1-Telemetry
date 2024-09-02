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

if [ "$machine" = "Mac" ]; then
    PICO_DIR="${1:-/Volumes/CIRCUITPY}"
    cp -r ${THISDIR}/lib/* ${PICO_DIR}/lib/
else
    PICO_DIR="${1:-/media/`whoami`/CIRCUITPY}"
    cp -RT "${THISDIR}/lib/" "${PICO_DIR}/lib"
fi

cat <<EOF > "${THISDIR}/settings.toml"
CIRCUITPY_WIFI_SSID = "${CIRCUITPY_WIFI_SSID:-AUXSPACE-METER}"
CIRCUITPY_WIFI_PASSWORD = "${CIRCUITPY_WIFI_PASSWORD:-12345678}"
EOF


cp "${THISDIR}/code.py" "${PICO_DIR}/"
