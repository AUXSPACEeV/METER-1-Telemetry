""" code.py

    Auxspace METER telemetry

    This project periodically collects sensoric data on a
    RaspberryPi Pico W and writes them to a Micro-SD card.

    The circuit:
        The MicroSD Breakout Board attaches to the SPI bus as follows:

        | Function      | Pin on RPI     |
        |:--------------|:---------------|
        | MOSI          | SPI0 TX (GP3)  |
        | MISO          | SPI0 RX (GP0)  |
        | CLK           | SPI0 SCK (GP2) |
        | CS (Micro-SD) | SPI0 CSn (GP1) |

        The other sensors attach to the I2C bus:

        | Function     | Pin on RPI |
        |:-------------|:-----------|
        | SCK (DPS310) | SCL (GP17) |
        | SCI (DPS310) | SDA (GP16) |
        | SCL (BOO08x) | SCL (GP17) |
        | SDA (BOO08x) | SDA (GP16) |

        Additional Pins are wired as seen below:

        | Source              | Function | Target    |
        |:--------------------|:--------:|:---------:|
        | BNO08x              | DI       | +3.3V     |
        | MicroSD             | CD       | RPI GP15  |
        | FTDI Adapter (opt.) | RXD      | RPI GP12  |
        | FTDI Adapter (opt.) | TXD      | RPI GP13  |

        Note: I2C SCL and SDA connections and the MicroSD CD Pin
            also have 10K Ohm pullup resistors.

        Note: Delete files on the SD card by connecting GP14 to 3V3.

    The software:
        In software, we want to periodically check sensor data and
        write it into a file called "data.txt".
        The data structure follows the InfluxDB Line protocol, to
        make it easy to parse into a time series database.
        Errors and logs will be written and appended to "run.log"
        and "error.log" respectively, containing the log level,
        message and a timestamp.
        Since the Pico's RTC is reset every time, the timestamps are
        relative to the board start, which is initialized on the
        1st of January 2020.
        For debugging purposes, messages are also logged onto the
        Serial console on UART0 via pins GP12 and GP13.

    created 01 Aug 2024
    by Maximilian Stephan for Auxspace eV.
"""
import os
import time

import adafruit_sdcard
import board
import busio
import digitalio
import storage
import wifi

from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import BNO_REPORT_ACCELEROMETER
from adafruit_dps310 import DPS310
from adafruit_connection_manager import get_radio_socketpool
from adafruit_httpserver import Server, Request, Response
from micropython import const  # type: ignore

# Soft access point configuration
NET_SSID: str = os.getenv("CIRCUITPY_WIFI_SSID", "AUXSPACE")
NET_PW: str = os.getenv("CIRCUITPY_WIFI_PASSWORD", "wifipassword")
NET_MAX_CON: const[int] = const(2)
NET_PORT: const[int] = const(80)

# SPI configuration
SPI_SCK: const = board.GP2
SPI_MISO: const = board.GP0
SPI_MOSI: const = board.GP3

# I2C configuration
I2C_RX: const = board.GP16
I2C_SCL: const = board.GP17

# UART configuration
UART_TX: const = board.GP12
UART_RX: const = board.GP13

# MicroSD configuration
MICROSD_CS: const = board.GP1
MICROSD_CD: const = board.GP15
MICROSD_DEL: const = board.GP14

MICROSD_CD_PIN: digitalio.DigitalInOut = digitalio.DigitalInOut(MICROSD_CD)
MICROSD_DEL_PIN: digitalio.DigitalInOut = digitalio.DigitalInOut(MICROSD_DEL)

# BNO08x configuration
BNO08X_I2C_ADDR: const[int] = const(0x4a)

# Configure FS
_SD_ROOT: const[str] = const("/sd")
_DATA_FILE: const[str] = const("data.txt")
_LOG_FILE: const[str] = const("run.log")
_ERR_FILE: const[str] = const("error.log")

DATAPATH: str = _SD_ROOT + "/" + _DATA_FILE
LOGPATH: str = _SD_ROOT + "/" + _LOG_FILE
ERRPATH: str = _SD_ROOT + "/" + _ERR_FILE


# Enums are not featured in circuitpython
class LogLevel:
    """Levels for the file, UART and STDOUT logger."""
    DEBUG: const[int] = const(0)
    INFO: const[int] = const(1)
    WARN: const[int] = const(2)
    ERROR: const[int] = const(3)

    @staticmethod
    def get_name(level: const[int]) -> str:
        # matching is a feature of python 3.10;
        # circuitpython 9 does not feature it yet.
        if level == LogLevel.DEBUG:
            return "DEBUG"
        if level == LogLevel.ERROR:
            return "ERROR"
        if level == LogLevel.WARN:
            return "WARN"
        if level == LogLevel.INFO:
            return "INFO"
        log(LogLevel.WARN, f"Log level {level} is unknown.")
        return "UNKNOWN"


# Enums are not featured in circuitpython
class SensorType:
    """Sensor types of this application."""
    BNO08X: const[int] = const(0)
    DPS310: const[int] = const(1)

    @staticmethod
    def get_name(sensor_type: const[int]) -> str:
        # matching is a feature of python 3.10;
        # circuitpython 9 does not feature it yet.
        if sensor_type == SensorType.BNO08X:
            return "bno08x"
        if sensor_type == SensorType.DPS310:
            return "dps310"
        log(LogLevel.ERROR, f"Sensor type {sensor_type} is unknown.")
        return "unknown"


class _SensorBase:
    """Base class representing relevant data from sensors."""

    # @abstractmethod is not featured in circuitpython
    def get_data(self) -> dict[str, float]:
        """Data getter for the influxDB line protocol.

        Returns:
            dict[str, float]: A dictionary with sensor data names and values
        """
        raise NotImplementedError("Abstract function has to be implemented.")


# @dataclass is not featured in circuitpython
class Bno08xData(_SensorBase):
    """Class representing relevant data from the Adafruit bno08x sensor."""

    def __init__(self, bno08x: BNO08X_I2C) -> None:
        self.bno08x: BNO08X_I2C = bno08x

    def get_data(self) -> dict[str, float]:
        data_dict = {
            "accel_x": 0,
            "accel_y": 0,
            "accel_z": 0,
        }
        acceleration = self.bno08x.acceleration
        if acceleration:
            accel_x, accel_y, accel_z = acceleration
            data_dict["accel_x"] = accel_x
            data_dict["accel_y"] = accel_y
            data_dict["accel_z"] = accel_z
        else:
            log(LogLevel.ERROR, "Could not get acceleration data from bno08x.")
        return data_dict

^
# @dataclass is not featured in circuitpython
class DPS310Data(_SensorBase):
    """Class representing relevant data from the Adafruit dps310 sensor."""

    def __init__(self, dps310: DPS310) -> None:
        self.dps310: DPS310 = dps310

    def get_data(self) -> dict[str, float]:
        # TODO: find out what data we need
        return {
            "pressure": self.dps310.pressure,
            "temp": self.dps310.temperature,
        }


# @dataclass is not featured in circuitpython
class SensorData:
    """Sensordata class with database-parsing interface.

    Args:
        sensor_type (SensorType): Type of the sensor
        data (_SensorBase): Data of the sensor as _SensorBase
        timestamp (int): Time in millis (can be relative time)
    """

    def __init__(
        self, sensor_type: SensorType, data: _SensorBase, timestamp: int
    ) -> None:
        self.sensor_type: SensorType = sensor_type
        self.data: _SensorBase = data
        self.timestamp: int = timestamp

    def to_influx_line(self) -> str | None:
        """Create a valid line in InfluxDB Line protocol from the SensorData.
        Note: This string ends with the timestamp, not a newline!

        Returns:
            str: If the sensor data is compatible with the protocol.
            None: If the sensor data is incompatible with the protocol.
        """
        # https://docs.influxdata.com/influxdb/cloud/reference/syntax/line-protocol/
        # <measurement>[,<tags>] <fields> <timestamp>
        # We don't use tags here, since we only have numerical data
        measurement = SensorType.get_name(self.sensor_type)
        _field_data: dict[str, float] = self.data.get_data()
        _field_substrings: list[str] = [
            f"{key}={value}"
            for key, value in _field_data.items()
        ]
        fields: str = ",".join(_field_substrings)

        return f"{measurement} {fields} {self.timestamp}"


# Initialize UART this early to make sure it exists in log()
# This uart is using GPIO Pins, the default debug port
# is used by the print() statements.
# This one is valuable when the board is hooked up to batteries
# and you don't want to interfere with the USB voltage on the main port.
UART: busio.UART | None = None

try:
    UART = busio.UART(UART_TX, UART_RX, baudrate=115200)
except Exception as e:
    print(f"Could not initialize UART: ", e)


def log(level: LogLevel = LogLevel.INFO, *message: str):
    """Log a message to the log file, UART and "STDOUT".

    Args:
        level (LogLevel): Level of the log message. Defaults to LogLevel.INFO
        message (tuple[str, ...]): Message(s) to log. Defaults to "".
    """
    str_message: str = ""
    logfile_path: str = LOGPATH

    # Only use logging format, if the message is not empty
    if message:
        # Combine all strings to one
        str_message = "".join([m for m in message])

        # Append a timestamp. This does not have to be this accurate
        _timestamp: int = int(time.monotonic() * 1_000)
        _level_name: str = LogLevel.get_name(level)
        str_message = f"[{_level_name}] - [{_timestamp}]: {str_message}"

    print(str_message)

    if UART:
        UART.write(str_message + "\r\n")

    # Debug messages are not written to the file.
    if level == LogLevel.DEBUG:
        return
    if level == LogLevel.ERROR:
        logfile_path = ERRPATH

    try:
        with open(logfile_path, "a") as logfile:
            logfile.write(str_message + "\r\n")
    except FileNotFoundError:
        print(f"Could not open file {logfile_path}: File not found.")
    except IOError as e:
        print(f"Could not write to {logfile_path}: ", e)
    except Exception as e:
        print(f"Writing to {logfile_path} failed: ",e)


def _print_directory(path: str, tabs: int = 0, use_logger: bool = False):
    """Pretty print files in a directory.

    Args:
        path (str): Path of the directory to print
        tabs (int): Number of tabs to display. Defaults to 0.
    """
    for file in os.listdir(path):
        if file == "?":
            continue  # Issue noted in Learn
        stats = os.stat(path + "/" + file)
        filesize = stats[6]
        isdir = stats[0] & 0x4000

        if filesize < 1_000:
            sizestr = str(filesize) + " by"
        elif filesize < 1_000_000:
            sizestr = f"{round(filesize / 1_000, 2)} KB"
        else:
            sizestr = f"{round(filesize / 1_000_000, 2)} MB"

        prettyprintname = ""
        for _ in range(tabs):
            prettyprintname += "   "
        prettyprintname += file
        if isdir:
            prettyprintname += "/"
        file_str: str = (
            '{0:<40} Size: {1:>10}'.format(prettyprintname, sizestr)
        )
        if use_logger:
            log(LogLevel.INFO, file_str)
        else:
            print(file_str)

        # recursively print directory contents
        if isdir:
            _print_directory(path + "/" + file, tabs + 1)


def init_access_point():
    """Initialize wifi.radio as soft access point."""
    wifi.radio.start_ap(
        ssid=NET_SSID, password=NET_PW, max_connections=NET_MAX_CON
    )
    log(LogLevel.INFO, "Access point created.")
    log(LogLevel.DEBUG, f"SSID: {NET_SSID}, password: {NET_PW}")


def init_i2c() -> busio.I2C:
    """Initialize the I2C bus.

    Returns:
        busio.I2C: reference to the RPI Pico's I2C bus interface.
    """

    log(LogLevel.INFO, "Initializing the I2C bus ...")
    i2c: busio.I2C = busio.I2C(I2C_SCL, I2C_RX)
    addr: list[str] = []

    # Get the lock before scanning
    while not i2c.try_lock():
        pass

    try:
        # Print all addresses on the I2C bus.
        addr = [hex(device_address) for device_address in i2c.scan()]
    finally:  # unlock the i2c bus when ctrl-c'ing out of the loop
        i2c.unlock()

    log(LogLevel.INFO, f"I2C addresses found: {addr}\r\n")
    return i2c


def init_spi() -> busio.SPI:
    """Initialize the SPI bus.

    Returns:
        busio.SPI: reference to the RPI Pico's SPI bus interface.
    """
    # "log" cannot be used since sd card board is not setup yet
    print("Initializing the SPI bus ...\n")
    return busio.SPI(SPI_SCK, MOSI=SPI_MOSI, MISO=SPI_MISO)


def init_microsd(spi_bus: busio.SPI) -> adafruit_sdcard.SDCard:
    """Initialize the Adafruit MicroSD card breakout board+ via SPI.

    Args:
        spi_bus (busio.SPI): SPI bus reference.

    Returns:
        adafruit_sdcard.SDCard: reference to the adafruit sdcard (SPI)
            interface.
    """
    # "log" cannot be used since sd card board is not setup yet
    print("Initializing MicroSD card ...")

    MICROSD_CD_PIN.direction = digitalio.Direction.INPUT
    MICROSD_CD_PIN.pull = digitalio.Pull.UP

    if not MICROSD_CD_PIN.value:
        print("Make sure to insert a MicroSD card! Trying again ...")

    while not MICROSD_CD_PIN.value:
        pass
    print("Card is connected. Establishing SPI connection ...")

    sd_cs: digitalio.DigitalInOut = digitalio.DigitalInOut(MICROSD_CS)

    sd_card: adafruit_sdcard.SDCard = adafruit_sdcard.SDCard(spi_bus, sd_cs)
    vfs: storage.VfsFat = storage.VfsFat(sd_card)  # type: ignore

    print(f"Mounting vfs at {_SD_ROOT}")

    storage.mount(vfs, _SD_ROOT)

    print()
    print("Files on filesystem:")
    print("====================")
    _print_directory(_SD_ROOT)
    print()

    return sd_card


def data2datafile(sensor_data: SensorData):
    """Write data to the data file in InfluxDB line protocol.

    Args:
        sensor_data (SensorData): Data to write to the file.
    """
    # Format sensor data to single InfluxDB Line
    if influx_line := sensor_data.to_influx_line():
        with open(DATAPATH, "a") as datafile:
            log(
                LogLevel.DEBUG,
                f"Appending '{sensor_data.to_influx_line()}' to {DATAPATH}",
            )
            datafile.write(influx_line + "\r\n")


def init_bno08x(
    i2c_bus: busio.I2C, report: int = BNO_REPORT_ACCELEROMETER
) -> BNO08X_I2C:
    """Initialize the Adafruit BNO08x sensor.

    Args:
        i2c_bus (busio.I2C): Reference to the RPI Pico's I2C bus interface.
        report (int): Report of the sensor to use.
            Defaults to BNO_REPORT_GAME_ROTATION_VECTOR.

    Returns:
        BNO08X_I2C: Reference to the BNO08x sensor (I2C) interface.
    """
    log(LogLevel.INFO, "Initializing BNO08x sensor ...")
    bno: BNO08X_I2C = BNO08X_I2C(i2c_bus, address=BNO08X_I2C_ADDR)
    bno.enable_feature(report)
    log(LogLevel.INFO, "Done.\r\n")

    return bno


def init_dps310(i2c_bus: busio.I2C) -> DPS310:
    """Initialize the Adafruit DPS310 sensor.

    Args:
        i2c_bus (busio.I2C): Reference to the RPI Pico's I2C bus interface.

    Returns:
        DPS310: Reference to the DPS310 sensor (I2C) interface.
    """
    log(LogLevel.INFO, "Initializing DPS310 sensor ...")
    dps: DPS310 = DPS310(i2c_bus)
    log(LogLevel.INFO, "Done.\r\n")

    return dps


def handle_sd():
    """handler for MicroSD Breakout board.
    This only checks if an SD Card is inserted
    and deletes the all files if the MICROSD_DEL button is pressed.
    """
    delete_files: list[str] = [
        LOGPATH,
        ERRPATH,
        DATAPATH,
    ]
    if not MICROSD_CD_PIN.value:
        log(LogLevel.ERROR, "No MicroSD card inserted.")

    if MICROSD_DEL_PIN.value:
        log(LogLevel.INFO, "MICROSD_DEL pressed. Deleting all files.")

        for path in delete_files:
            try:
                log(LogLevel.DEBUG, f"Removing file {path}.")
                os.remove(path)
            except FileNotFoundError:
                log(LogLevel.WARN, f"File {path} does not exist.")

        log(LogLevel.INFO, "File deletion completed.")


def _handle_sensor(sensor_type: SensorType, data: _SensorBase):
    """Generic handler function for sensors.

    Args:
        sensor_type (SensorType): Type of the sensor.
        data (_SensorBase): Sensor data
    """
    # TODO: more accurate timestamps (optional)
    current_time: int =  int(time.monotonic() * 1_000)
    sensor_data: SensorData = SensorData(sensor_type, data, current_time)
    data2datafile(sensor_data)


def handle_bno08x(bno08x: BNO08X_I2C):
    """Handle the BNO08x Data.

    Args:
        bno08x (BNO08X_I2C): Reference to the BNO08x sensor (I2C) interface.
    """
    # Get the gyro data with timestamps and write it to DB file
    bno_data: Bno08xData = Bno08xData(bno08x)
    _handle_sensor(SensorType.BNO08X, bno_data)


def handle_dps310(dps310: DPS310):
    """Handle the DPS310 Data.

    Args:
        dps310 (DPS310): Reference to the DPS310 sensor (I2C) interface.
    """
    # Get the temp and humidity data with timestamps and write it to DB file
    dps_data: DPS310Data = DPS310Data(dps310)
    _handle_sensor(SensorType.DPS310, dps_data)


def _init_peripherals():
    """Initialize all peripherals that this program uses.

    Returns:
        adafruit_sdcard.SDCard: Reference to the MicroSD (SPI) interface.
        BNO08X_I2C: Reference to the BNO08x sensor (I2C) interface.
        DPS310: Reference to the DPS310 sensor (I2C) interface.
    """
    # Initialize SPI at first, since the microSD card is used for
    # logging.
    spi: busio.SPI = init_spi()
    sd_card: adafruit_sdcard.SDCard = init_microsd(spi)

    # Start WiFi Access point directly after
    init_access_point()

    # I2C is on the next priority, since the sensors connect to it
    i2c: busio.I2C = init_i2c()

    bno: BNO08X_I2C = init_bno08x(i2c)

    dps: DPS310 = init_dps310(i2c)

    # Initialize MICROSD_DEL input pin
    MICROSD_DEL_PIN.direction = digitalio.Direction.INPUT
    MICROSD_DEL_PIN.pull = digitalio.Pull.DOWN

    log(LogLevel.INFO, "Peripheral initialization complete.\r\n")
    return sd_card, bno, dps


# Updated function to handle file download as a stream
def handle_file_stream(request: Request, file_name: str):
    """Serve a file as a stream to the client for download.

    Args:
        request (Request): Request from the client
        file_name (str): Name of the file in _SD_ROOT to be downloaded
    """
    file_path: str= f"{_SD_ROOT}/{file_name}"
    try:
        # Open the file in binary read mode
        with open(file_path, "rb") as file:
            request.connection.send(
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/octet-stream\r\n"
                f"Content-Disposition: attachment; filename=\"{file_name}\"\r\n"
                "Connection: close\r\n\r\n"
            )

            while True:
                # Read a chunk of the file (e.g., 512 bytes)
                chunk = file.read(512)
                if not chunk:
                    break
                request.connection.send(chunk)

    except Exception as e:
        # Send a 500 response if there's an error
        request.connection.send(
            "HTTP/1.1 500 Internal Server Error\r\n"
            "Content-Type: text/plain\r\n"
            "Connection: close\r\n\r\n"
            f"Error: {str(e)}"
        )

    finally:
        request.connection.close()


def webpage():
    text_list: list[str] = [
        f'<li>{filename} - <a href="{_SD_ROOT}/{filename}">Download</a> - <a href="/delete/{filename}">Delete</a></li>'
        for filename in os.listdir(_SD_ROOT)
        if filename != "?"
    ]
    text_str = "<ul>" if len(text_list) > 0 else f"<p> No files to list in {_SD_ROOT}.</p>"
    text_str += "\n".join(text_list)
    text_str += "</ul>" if len(text_list) > 0 else ""
    html = f"""<!DOCTYPE html>
    <html>
        <head>
            <meta http-equiv="Content-type" content="text/html;charset=utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <title>Auxspace Telemetry Interface</title>
            <h1>Auxspace Telemetry Interface</h1>
            <br>
            <p class="dotted">This page allows you download and delete files from the SD Card on the Telemetry device.</p>
            {text_str}
        </body>
    </html>
    """
    return html


def _init_webserver() -> Server:
    """Initialize the status webserver.

    Returns:
        Server: Configured webserver
    """
    log(LogLevel.INFO, "Starting server..")
    pool = get_radio_socketpool(wifi.radio)
    server: Server = Server(pool, "/")

    #  route default static IP
    @server.route("/")
    def base(request: Request):
        """Serve WEBPAGE at webserver root.

        Args:
            request (Request): Request from the client
        """
        #  serve the HTML f string
        #  with content type text/html
        log(LogLevel.DEBUG, f"Serving main page to {request.client_address}")
        return Response(request, f"{webpage()}", content_type='text/html')

    # Route for downloading files from the SD card
    @server.route(f"{_SD_ROOT}/<filename>")
    def download_file(request: Request, filename: str):
        """Serve a file from the SD card as a download.

        Args:
            request (Request): Request from the client
            filename (str): Name of the file to download
        """
        log(LogLevel.DEBUG, f"Requesting {filename} for download")
        return handle_file_stream(request, filename)

    # Route for downloading files from the SD card
    @server.route(f"/delete/<filename>")
    def handle_file_delete(request: Request, filename: str):
        """Delete a file from the SD card when requested.

        Args:
            request (Request): Request from the client
            filename (str): Name of the file to be deleted
        """
        file_path: str = f"{_SD_ROOT}/{filename}"
        try:
            os.remove(file_path)
            log(LogLevel.INFO, f"File {file_path} deleted.")

            # Send a success response
            request.connection.send(
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain\r\n"
                "Connection: close\r\n\r\n"
                f"File '{filename}' deleted successfully."
            )
        except Exception as e:
            # Send a 500 response if there's an error
            request.connection.send(
                "HTTP/1.1 500 Internal Server Error\r\n"
                "Content-Type: text/plain\r\n"
                "Connection: close\r\n\r\n"
                f"Error deleting file '{filename}': {str(e)}"
            )
        finally:
            # Close the connection after handling the request
            request.connection.close()
    return server


def loop(sd: adafruit_sdcard.SDCard, bno: BNO08X_I2C, dps: DPS310):
    """Arduino-like loop function.
    Endlessly gets looped in intervalls.

    Args:
        sd (adafruit_sdcard.SDCard): Reference to the MicroSD (SPI) interface.
        bno (BNO08X_I2C): Reference to the BNO08x sensor (I2C) interface.
        dps (DPS310): Reference to the DPS310 sensor (I2C) interface.
    """
    handle_sd()
    # Handle sensors one by one.
    # TODO: Upgrade this to event-based data gathering in the future.
    handle_dps310(dps)
    handle_bno08x(bno)


def main():
    """Main entrypoint of the circuitpython telemetry program."""
    # Initialize peripherals at first (comparable to arduino setup())
    sd, bno, dps = _init_peripherals()
    server: Server = _init_webserver()
    ip = str(wifi.radio.ipv4_address_ap)

    try:
        server.start(ip, NET_PORT)
        log(LogLevel.INFO, f"Serving default WEBPAGE at {ip}:{NET_PORT}")
    # I know this is too broad, but currently its necessary for fail-safety
    except Exception as e:
        log(LogLevel.ERROR, f"Unexpected Error occured in main function: {e}")

    while True:

        try:
            server.poll()
            loop(sd, bno, dps)
        # I know this is too broad, but currently its necessary for fail-safety
        except Exception as e:
            log(LogLevel.ERROR, f"Unexpected Error occured in main function: {e}")


# Entrypoint
if __name__ == "__main__":
    main()
