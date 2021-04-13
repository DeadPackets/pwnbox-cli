# pwnbox-cli

![GitHub](https://img.shields.io/github/license/deadpackets/pwnbox-cli) ![GitHub Workflow Status](https://img.shields.io/github/workflow/status/deadpackets/pwnbox-cli/publish-package-on-release) ![GitHub last commit](https://img.shields.io/github/last-commit/deadpackets/pwnbox-cli) ![GitHub release (latest by date)](https://img.shields.io/github/v/release/deadpackets/pwnbox-cli) ![GitHub issues](https://img.shields.io/github/issues/deadpackets/pwnbox) ![PyPI - Downloads](https://img.shields.io/pypi/dm/pwnbox) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pwnbox) ![PyPI - Wheel](https://img.shields.io/pypi/wheel/pwnbox)

<p align="center">

<img src="https://github.com/DeadPackets/pwnbox-cli/raw/main/demo.gif">

</p>

The CLI tool that lets you easily deploy, customize and manage PwnBox.

## Features

* A fully customizable deployment of PwnBox using a config file.
* Automatic update checks for newer PwnBox images and CLI.
* Verbose output so you can tell what commands are being run.
* Easy deployment and teardown of PwnBox containers.
* View image download progress in real-time.
* Cool ASCII banners.

## Installation

Using Python >= 3.6, you can install this CLI using pip directly:

```bash
pip install pwnbox
```

And that's it! You're all set to use PwnBox CLI!

## Usage

```bash
$ pwnbox -h # or --help
usage: pwnbox [-h] [-v] [--version] [-b] [-n] [-c CONFIG] [-t TIMEOUT] COMMAND

Launch and manage PwnBox containers.

positional arguments:
  COMMAND               The action to perform.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Enable verbose output.
  --version             Print the current version of the program.
  -b, --no-banner       Disable printing the banner.
  -n, --no-update       Disable the automatic check for newer PwnBox versions.
  -c CONFIG, --config CONFIG
                        Specify the path to a PwnBox config file.
  -t TIMEOUT, --timeout TIMEOUT
                        Specify the timeout of waiting for SSH to be available.

Commands:
  up                    Starts the PwnBox container if not already started, and connects to it.
  down                  Stop the PwnBox container.
  pull                  Download the latest PwnBox image.
  generate              Write the default config to a file.
```

## Configuration

All configuration of the PwnBox container can be done from `pwnbox.conf`, which is by default stored (and created on first run) at `$HOME/.pwnbox/pwnbox.conf`.

The configuration file syntax is as follows:

```bash
[IMAGE]
# Where to pull the image from, can be 'ghcr.io' or 'registry.hub.docker.com'
DOCKER_REPOSITORY=registry.hub.docker.com
# The tag of the image to pull. Can be any specific version you'd like
IMAGE_TAG=latest

[CONTAINER]
# Name of the container that Docker will give
NAME=pwnbox
# Hostname inside the container
HOSTNAME=pwnbox
# Should the container run privileged?
PRIVILEGED=true
# Should the container be removed when stopped?
AUTO_REMOVE=true
# Enable this to run GUI applications outside the container
X11_FORWARDING=true
# Enable this to automatically forward all ports and have direct interace access (only linux)
HOST_NETWORKING=true
# What ports would you like forwarded? (syntax HOST:CONTAINER with multiple ones being comma seperated)
# Should keep 2222 for SSH port
FORWARDED_PORT=2222:2222,9000-9010:9000-9010
# Where to store the data thats from /mnt/external
EXTERNAL_VOLUME=$HOME/.pnbox/external
# Where to fetch public ssh keys from
SSH_VOLUME=$HOME/.ssh
```

You can always re-generate this file using `pwnbox generate` and copy it to other places to have multiple configurations.

## How It Works

When bringing up a container, the CLI will:

1. Check if Docker is accesible
2. Check if the desired PwnBox image is downloaded
   1. If it is, check if there is a newer version of the PwnBox image
   2. If not, download the latest version available of the image
3. Bring up the PwnBox container with the desired settings
   1. If X11 Forwarding is enabled, `xhost` is executed to whitelist remote connections from localhost
4. Wait for SSH to be available, then SSH into the container

## Contributions

PRs are more than welcome! Fix bugs, add features, improve speed or anything else. I will gladly merge them once I have reviewed them.

