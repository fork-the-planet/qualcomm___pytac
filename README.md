# PyTAC

Python implementation of Test Automation Controller (TAC/Alpaca) for controlling Qualcomm debug boards.
It uses config files and PSOC firmware from the original TAC (Alpaca) system.

# Installation

Install the `pytac` command on your system with [pipx](https://pipx.pypa.io):

    pipx install .

This puts a single `pytac` entry point on your `PATH`. Note that the `hid`
dependency needs `libhidapi` package to be installed (required for Bughopper V2 boards).

Alternatively, for development in a virtualenv:

    virtualenv -p python3 venv
    . ./venv/bin/activate
    pip install -e .

Run `pytac -h` to see all available options.

## USB permissions

By default, USB devices are not accessible without root. Create a udev rule for your board:

    echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", ATTR{idProduct}=="9302", MODE="0666", GROUP="plugdev"' \
      | sudo tee /etc/udev/rules.d/99-alpaca.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger

Then make sure your user is in the `plugdev` group (log out and back in after):

    sudo usermod -aG plugdev $USER

# Configuration

**Bughopper boards (V1 and V2) work out of the box.** They are self-describing and need no
config files.

**All other debug boards (FTDI, PSOC) require configuration files** that are NOT shipped with
pytac. You must obtain them yourself before these boards will work:

1. Copy the `configurations/` directory (the `.tcnf` files and `devicelist.json`) from the
   [qcom-test-automation-controller](https://github.com/qualcomm/qcom-test-automation-controller/tree/main/configurations)
   project into a directory of your choice.
2. Point pytac at that directory with `--tac-config-path <dir>`.

Note: some configs in qcom-test-automation-controller currently have syntax issues; pick the
ones that match your board.

`devicelist.json` maps board hardware IDs to their `.tcnf` config files, and must be present in
the `--tac-config-path` directory for FTDI/PSOC boards. Example entry for a PSOC board:

    {
      "catalog": [
        {
          "platform_id": 17,
          "configPath": "tac_configs/TAC_PSOC_17.tcnf"
        }
      ]
    }

## Finding your board's serial number

The `--serial` argument takes the USB serial number, not a device path. Find it with:

    udevadm info /dev/ttyACM0 | grep ID_SERIAL_SHORT

Or using `lsusb` (replace `VID:PID` with `0403:6011` for FTDI or `05c6:9302` for PSOC):

    lsusb -v -d VID:PID | grep iSerial

# Using as a shell

The shell is the default mode, so `--shell` is optional:

    pytac --serial <ID_SERIAL_SHORT>

Optional arguments:

    --tac-config-path <dir>   # path to config directory (required for FTDI/PSOC boards, see Configuration)
    --log-level DEBUG         # log verbosity (default: DEBUG)

Once started, the shell prompt accepts commands generated from your board's config script. The available commands depend on the config — not all boards define every command (e.g. newer configs may omit `powerOn`/`powerOff`). Typical commands:

**Power control:**

    powerOn
    powerOff
    devicePowerOn
    devicePowerOff
    usbDevicePowerOn
    usbDevicePowerOff

**Boot modes:**

    bootToEDL
    bootToFastboot
    bootToUEFI
    reset

**GPIO pins** (use with `1` to assert, `0` to deassert):

    pkey 1      # press power key
    pkey 0      # release power key
    volup 1
    voldn 1

Type `help` in the shell to list all commands available for your specific board.

# Running a single command

Use `--oneshot` to run one command and exit, without entering the interactive shell. This is
handy for scripting:

    pytac --serial <ID_SERIAL_SHORT> --oneshot bootToEDL
    pytac --serial <ID_SERIAL_SHORT> --oneshot reset

GPIO pin commands take an integer value (`1` to assert, `0` to deassert):

    pytac --serial <ID_SERIAL_SHORT> --oneshot pkey 1
    pytac --serial <ID_SERIAL_SHORT> --oneshot pkey 0

The same commands available in the shell can be used here. An unknown command exits with an
error listing the commands supported by your board.

# Using as a service

    pytac --service --serial <ID_SERIAL_SHORT_1> [<ID_SERIAL_SHORT_2> ...]

The REST API runs on `http://localhost:5000`. Example usage with curl:

    # List connected boards
    curl http://localhost:5000/

    # List available quick methods (bootToEDL, powerOn, etc.)
    curl http://localhost:5000/<boardid>/quick

    # Power on/off
    curl -X PUT http://localhost:5000/<boardid>/quick/powerOn
    curl -X PUT http://localhost:5000/<boardid>/quick/powerOff

    # Boot to EDL
    curl -X PUT http://localhost:5000/<boardid>/quick/bootToEDL

    # Boot to fastboot
    curl -X PUT http://localhost:5000/<boardid>/quick/bootToFastboot

    # Set a named pin
    curl -X PUT "http://localhost:5000/<boardid>/command/reset?value=1"

    # Set a raw pin (e.g., bus A, pin 0)
    curl -X PUT "http://localhost:5000/<boardid>/pin/A0?value=1"

Note: REST API server runs in debug mode. Running with multiple concurrent threads may lead to unexpected behaviour.

# License

pytac is licensed under the [BSD-3-clause License](https://spdx.org/licenses/BSD-3-Clause.html). See [LICENSE](LICENSE) for the full license text.
