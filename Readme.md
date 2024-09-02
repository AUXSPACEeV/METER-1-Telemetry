# `Auxspace Telemetry`

> Rocket telemetry software running on a RaspberryPi Pico W

## Prerequisites

* RaspberryPi Pico W Board
* Adafruit DPS310 Barometric Sensor
* Adafruit BNO08x 9-DoF Orientation IMU Fusion Breakout Board
* Adafruit Micro-SD Breakout Board+
* FAT32-formatted Micro-SD Card (dos)

## Setup

### Hardware Setup

![hardware setup](/doc/img/RPIpicow-tele.drawio.png)

### Software Setup

This project was made using Adafruit's CircuitPython.

## Function

This program initializes the Micro-SD card and periodically writes
the data from the sensors onto it using the
[InfluxDB Line Protocol](https://docs.influxdata.com/influxdb/cloud/reference/syntax/line-protocol/).

The MicroSD Breakout board is communicating via SPI, while the other sensors
use I2C.

```bash
Initializing the SPI bus ...

Initializing MicroSD card ...
Card is connected. Starting SPI connection ...
Mounting vfs at /sd

Files on filesystem:
====================
run.log                                  Size:     1.8 MB
error.log                                Size:     650 by
data.txt                                 Size:    3.54 MB

[INFO] - [1577841648000]: Initializing the I2C bus ...
[INFO] - [1577841648000]: I2C addresses found: ['0x4b', '0x77']

[INFO] - [1577841648000]: Initializing BNO08x sensor ...
[INFO] - [1577841649000]: Done.

[INFO] - [1577841649000]: Initializing DPS310 sensor ...
[INFO] - [1577841650000]: Done.

[INFO] - [1577841650000]: Peripheral initialization complete.

[DEBUG] - [1577841650000]: Appending 'dps310 pressure=957.428,temp=27.7834 1577841650000' to /sd/data.txt
[DEBUG] - [1577841650000]: Appending 'bno08x i=-0.0306396,j=0.000183105,k=0.999512,real=-0.00793457 1577841650000' to /sd/data.txt
[DEBUG] - [1577841650000]: Appending 'dps310 pressure=957.427,temp=27.7976 1577841650000' to /sd/data.txt
[DEBUG] - [1577841650000]: Appending 'bno08x i=-0.0305176,j=0.000244141,k=0.999512,real=-0.00787354 1577841650000' to /sd/data.txt
[DEBUG] - [1577841650000]: Appending 'dps310 pressure=957.43,temp=27.8033 1577841650000' to /sd/data.txt
[DEBUG] - [1577841650000]: Appending 'bno08x i=-0.0301514,j=0.000183105,k=0.999512,real=-0.00793457 1577841650000' to /sd/data.txt
[DEBUG] - [1577841650000]: Appending 'dps310 pressure=957.429,temp=27.7945 1577841650000' to /sd/data.txt
[DEBUG] - [1577841651000]: Appending 'bno08x i=-0.0300293,j=0.000244141,k=0.999512,real=-0.00793457 1577841651000' to /sd/data.txt
```

## Circuitpython Setup

The following packages are required to setup the virtual environment:

- python3
- python3-pip
- python3-venv

```bash
# Create venv and get requirements
./scripts/setup.sh
# Actiate venv
. .venv/bin/activate
```

Also, the circuitpython `.uf2` file has to be flashed onto the RPI Pico once.

1. Get circuitpython for the PiPico W: <https://circuitpython.org/board/raspberry_pi_pico_w/>.
2. Press and hold the *BOOTSEL* button on the RPI Pico, connect it via micro USB to your host
machine and let go of the *BOOTSEL* button.
3. The RPI should now be visible as a mounted FS named `RPI_RP2`.
4. Copy the downloaded `.uf2` file to said `RPI_RP2` directory.
5. Wait until the copying is done and reconnect the Pi without holding the *BOOTSEL* button.
6. The process is done!
Use the terminal emulator of your choice to connect to the RPI Pico's Serial.
In this case, we will be using `picocom`.

## Usage

The following packages are required to deploy the codebase:

- picocom

```bash
# Terminal window 1
picocom -b 115200 $PICO_DEV

# Terminal window 2
./scripts/deploy.sh
```

## Webserver

This project also contains a webserver running on the RPI.
To get access, connect to the access point called `AUXSPACE-METER`.
The default password is set to `12345678`.
These values can be changed by calling `scripts/deploy.sh` with the
environment variables `CIRCUITPY_WIFI_PASSWORD` and `CIRCUITPY_WIFI_SSID`:

```bash
CIRCUITPY_WIFI_PASSWORD="mypasswd" \
    CIRCUITPY_WIFI_SSID="myssid" \
    ./scripts/deploy.sh
```

On the webserver, you can download and delete files from the SD-Card.
