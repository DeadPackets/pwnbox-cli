#!/usr/bin/env python
import argparse
import configparser
import math
import os
from pathlib import Path
from sys import exit as sys_exit
from sys import platform
from time import sleep

import docker
import requests
from packaging import version
from rich import print as pprint
from rich.console import Console
from rich.progress import BarColumn, Progress
from ssh_wait import ssh_wait

# Global Vars
VERSION = "v2.1.1"
console = Console()


# Bytes to Human Readable
def byte_to_human_read(byte):
	if byte == 0:
		raise ValueError("Size is not valid.")
	byte = int(byte)
	size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
	index = int(math.floor(math.log(byte, 1024)))
	power = math.pow(1024, index)
	size = round(byte / power, 2)
	return "{} {}".format(size, size_name[index])


# Main function
def main() -> None:
	# Initialize ArgParser
	class NoAction(argparse.Action):
		def __init__(self: "NoAction", **kwargs: str) -> None:
			kwargs.setdefault("default", argparse.SUPPRESS)
			kwargs.setdefault("nargs", 0)
			super(NoAction, self).__init__(**kwargs)

		def __call__(
			self: "NoAction",
			parser: str,
			namespace: str,
			values: str,
			option_string: str = None,
		) -> None:
			pass

	parser = argparse.ArgumentParser(description="Launch and manage PwnBox containers.")
	parser.register("action", "none", NoAction)

	# Main arguments
	parser.add_argument(
		"command",
		metavar="COMMAND",
		help="The action to perform.",
		choices=["up", "down", "pull", "generate"],
	)
	parser.add_argument(
		"-v",
		"--verbose",
		help="Enable verbose output.",
		action="store_true",
	)
	parser.add_argument(
		"--version",
		help="Print the current version of the program.",
		action="version",
		version=f"{VERSION}",
	)
	parser.add_argument(
		"-b",
		"--no-banner",
		help="Disable printing the banner.",
		action="store_true",
	)
	parser.add_argument(
		"-n",
		"--no-update",
		help="Disable the automatic check for newer PwnBox versions.",
		action="store_true",
	)
	parser.add_argument(
		"-c",
		"--config",
		help="Specify the path to a PwnBox config file.",
		default=f"{os.getenv('HOME')}/.pwnbox/pwnbox.conf",
	)
	parser.add_argument(
		"-t",
		"--timeout",
		help="Specify the timeout of waiting for SSH to be available.",
		type=int,
		default=10,
	)
	parser.add_argument(
		"-s",
		"--no-ssh",
		help="Do not SSH into the container after bringing it up.",
		action="store_true"
	)

	# Possible commands
	group = parser.add_argument_group(title="Commands")
	group.add_argument(
		"up",
		help="Starts the PwnBox container if not already started, and connects to it.",
		action="none",
	)
	group.add_argument("down", help="Stop the PwnBox container.", action="none")
	group.add_argument("pull", help="Download the latest PwnBox image.", action="none")
	group.add_argument(
		"generate",
		help="Write the default config to a file.",
		action="none",
	)

	# Parse Args
	args = parser.parse_args()

	# Verbose printing function
	def verbose_print(string: str) -> None:
		if args.verbose:
			pprint(string)

	# Print the ascii header
	if not args.no_banner:
		banner = f"""
{' '*4}██████╗ ██╗    ██╗███╗   ██╗██████╗  ██████╗ ██╗  ██╗
{' '*4}██╔══██╗██║    ██║████╗  ██║██╔══██╗██╔═══██╗╚██╗██╔╝
{' '*4}██████╔╝██║ █╗ ██║██╔██╗ ██║██████╔╝██║   ██║ ╚███╔╝
{' '*4}██╔═══╝ ██║███╗██║██║╚██╗██║██╔══██╗██║   ██║ ██╔██╗
{' '*4}██║     ╚███╔███╔╝██║ ╚████║██████╔╝╚██████╔╝██╔╝ ██╗
{' '*4}╚═╝      ╚══╝╚══╝ ╚═╝  ╚═══╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝
	"""
		pprint(f"[red]{banner}[/red]")
		# Fancy small calculation to center the subtitle
		subtitle = f"[cyan]{VERSION}[/cyan] - Made by @DeadPackets"
		padding = len(banner.split("\n")[1])
		pprint(f"[blue]{subtitle.center(padding)}[/blue]\n")

	# Attempt to read the config file
	config = configparser.ConfigParser()
	args.config = os.path.expandvars(args.config)
	if args.command != "generate":
		if os.path.isfile(args.config):
			try:
				config.read(args.config)
			except configparser.Error:
				pprint("[red]=> Error: Cannot read or parse config file!")
				sys_exit(1)
		elif args.config == f"{os.getenv('HOME')}/.pwnbox/pwnbox.conf":
			pprint(f"[cyan]=> Creating default config at {args.config}")
			Path(args.config).parent.mkdir(exist_ok=True)
			conf_file = open(f"{os.path.dirname(__file__)}/pwnbox.conf", "r").read()
			open(args.config, "w").write(conf_file)
			config.read(args.config)
		else:
			pprint(f'[red]=> Error: "{args.config}" does not exist![/red]')
			sys_exit(1)

	# Check if a newer version has been released
	if not args.no_update:
		try:
			git_version = requests.get(
				"https://raw.githubusercontent.com/DeadPackets/pwnbox-cli/main/VERSION.txt",
			).text.strip()
			if version.parse(git_version) > version.parse(VERSION):
				pprint(
					f"[cyan]=> A new version of PwnBox CLI ({git_version}) has been released. Upgrade to get the latest features and fixes.[/cyan]",
				)
		except (requests.exceptions.RequestException, version.InvalidVersion):
			pprint(
				"[red]=> Error: There was an error trying to check GitHub for the latest version.[/red]",
			)

	# Test if we have access to docker
	try:
		client = docker.from_env()
		client.ping()
	except (docker.errors.DockerException, docker.errors.APIError):
		pprint(
			"[red]=> Error: Could not connect to Docker. Check if you have Docker installed and running.[/red]",
		)
		sys_exit(1)

	# If the command is "UP"
	if args.command == "up":
		# Check if the container is running
		try:
			if client.containers is None:
				pprint(
					"[red]=> Error: Could not connect to Docker. Check if you have Docker installed and running.[/red]",
				)
				sys_exit(1)
			pwnbox_container = client.containers.get(config["CONTAINER"]["NAME"])
			pprint("[blue]=> PwnBox container already running! Logging in...[/blue]")
		except docker.errors.NotFound:
			# Test if we have the image downloaded
			container_image = f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}"
			pprint(f"[magenta]=> Image {container_image} selected...[/magenta]")
			try:
				pprint("[blue]=> Image already downloaded, continuing...[/blue]")
				# Grab local image
				local_image = client.images.get(container_image)

				# Grab registry data
				if not args.no_update:
					with console.status(
						"[cyan]=> Checking for newer PwnBox images...[/cyan]",
						spinner="dots",
					):
						registry_data = client.images.get_registry_data(
							f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}",
						)
					if (
						local_image.attrs["RepoDigests"][0].split("@")[1]
						!= registry_data.id
					):
						pprint(
							'[yellow]=> A newer version of the PwnBox container is available! Run "pwnbox pull" to update.[/yellow]',
						)
			except docker.errors.ImageNotFound:
				pprint(
					"[yellow]=> PwnBox image not found locally, pulling image...[/yellow]",
				)
				pull_progress = client.api.pull(
					f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox",
					tag=config["IMAGE"]["IMAGE_TAG"],
					stream=True,
					decode=True,
				)
				with Progress(
					"[progress.description]{task.description}",
					BarColumn(),
					"[progress.percentage]{task.percentage:>3.0f}%",
				) as progress:
					tasks = {}
					for _s in pull_progress:
						if "progressDetail" in _s:
							if _s["progressDetail"] != {}:
								if _s["id"] in tasks:
									if (
										_s["progressDetail"]["current"]
										== _s["progressDetail"]["total"]
									):
										progress.update(
											tasks[_s["id"]]["rich_task"],
											description=f"[dim green]Downloaded layer {_s['id']} [bold][{byte_to_human_read(_s['progressDetail']['total'])}][/bold][/dim green]",
											advance=(
												_s["progressDetail"]["current"]
												- tasks[_s["id"]]["progress"]["current"]
											),
										)
									else:
										progress.update(
											tasks[_s["id"]]["rich_task"],
											description=f"[dim {'blue' if _s['status'] == 'Downloading' else 'cyan'}]{_s['status']} layer {_s['id']} [bold][{byte_to_human_read(_s['progressDetail']['total'])}][/bold][/dim {'blue' if _s['status'] == 'Downloading' else 'cyan'}]",
											advance=(
												_s["progressDetail"]["current"]
												- tasks[_s["id"]]["progress"]["current"]
											),
										)
										tasks[_s["id"]]["progress"] = _s[
											"progressDetail"
										]
								else:
									tasks[_s["id"]] = {}
									tasks[_s["id"]]["progress"] = _s["progressDetail"]
									tasks[_s["id"]]["rich_task"] = progress.add_task(
										f"[dim blue]{_s['status']} layer {_s['id']} [bold][{byte_to_human_read(_s['progressDetail']['total'])}][/bold][/dim blue]",
										total=_s["progressDetail"]["total"],
									)
									progress.update(
										tasks[_s["id"]]["rich_task"],
										advance=_s["progressDetail"]["current"],
									)
				pprint("[green]=> PwnBox image downloaded successfully![/green]")

			# Run the container
			try:
				# Prepare environment variables
				env_vars = {}
				if config["CONTAINER"]["X11_FORWARDING"].lower() == "true":
					is_linux = platform in ("linux", "linux2")
					with console.status(
						"[cyan]=> Allowing X11 remote access...[/cyan]",
					):
						if is_linux:
							os.system("xhost +local:root +localhost >/dev/null 2>/dev/null")
						else:
							os.system("xhost +localhost >/dev/null 2>/dev/null")
					pprint("[blue]=> X11 remote access enabled.[/blue]")

				# Forward ports
				forwarded_ports = {}
				for part in config["CONTAINER"]["FORWARDED_PORT"].split(","):
					# Okay this is gonna be sort of complex
					container_ports, host_ports = part.split(":")
					if "-" not in container_ports:
						forwarded_ports[f"{container_ports}/tcp"] = int(host_ports)
					else:
						container_port_range = range(
							int(container_ports.split("-")[0]),
							int(container_ports.split("-")[1]) + 1,
						)
						host_port_range = range(
							int(host_ports.split("-")[0]),
							int(host_ports.split("-")[1]) + 1,
						)
						if len(container_port_range) == len(host_port_range):
							for container_port, host_port in zip(
								container_port_range,
								host_port_range,
							):
								forwarded_ports[f"{container_port}/tcp"] = host_port
						else:
							pprint(
								f'[red]=> Error: Invalid port mapping "{part}"! Exiting...[/red]',
							)
							sys_exit(1)

				# Volumes
				volume_config = {
					os.path.expandvars(config["CONTAINER"]["EXTERNAL_VOLUME"]): {
						"bind": "/mnt/external",
						"mode": "rw",
					},
					os.path.expandvars(config["CONTAINER"]["SSH_VOLUME"]): {
						"bind": "/opt/ssh",
						"mode": "rw",
					},
				}

				# Add X11 forwarding info on linux
				if is_linux:
					volume_config["/tmp/.X11-unix"] = {
						"bind": "/tmp/.X11-unix",
						"mode": "rw",
					}

				container_id = client.containers.run(
					container_image,
					auto_remove=config["CONTAINER"]["AUTO_REMOVE"].lower() == "true",
					extra_hosts={
						"host.docker.internal": "192.168.65.2"
					},  # NOTE: Docker needs to add a way to get host address reliably first.
					detach=True,
					dns=config["CONTAINER"]["DNS_SERVERS"].split(","),
					environment=env_vars,
					hostname=config["CONTAINER"]["HOSTNAME"],
					ports=forwarded_ports
					if config["CONTAINER"]["HOST_NETWORKING"].lower() != "true"
					else {},
					privileged=config["CONTAINER"]["PRIVILEGED"].lower() == "true",
					remove=config["CONTAINER"]["AUTO_REMOVE"].lower() == "true",
					name=config["CONTAINER"]["NAME"],
					network_mode="host"
					if (
						config["CONTAINER"]["HOST_NETWORKING"].lower() == "true"
						and is_linux
					)
					else "bridge",
					volumes=volume_config,
				)

				verbose_print(
					f"[cyan]=> Container has been launched with ID: {container_id.short_id}[/cyan]"
				)
				pprint("[green]=> PwnBox launched successfully![/green]")
			except docker.errors.APIError:
				pprint(
					"[red]=> Error: There was an error launching the PwnBox container. Exiting..."
				)
				sys_exit(1)

		# Wait for SSH
		with console.status(
			"[blue]=> Waiting for SSH to be available...[/blue]", spinner="dots"
		):
			sleep(1)  # FIXME: Figure out a better way than hardcoded sleep
			ssh_result = ssh_wait(
				"127.0.0.1", service=2222, wait_limit=args.timeout * 10, log_fn=None
			)
		if ssh_result == 0:
			if args.no_ssh:
				pprint("[green]=> PwnBox launched successfully!")
				sys_exit(0)
			# SSH into the container
			pprint("[green]=> SSH available! Logging in...[/green]")
			os.execlp("ssh", "-oStrictHostKeyChecking=no", "-X", "root@127.0.0.1", "-p 2222")
		else:
			pprint(
				"[red]=> Error: Timeout waiting for SSH to available in PwnBox.[/red]"
			)
			sys_exit(1)
	elif args.command == "down":
		# Check if the container is running
		try:
			pwnbox_container = client.containers.get(config["CONTAINER"]["NAME"])
			with console.status("[cyan]=> Disabling X11 remote access...[/cyan]"):
				if platform in ("linux", "linux2"):
					os.system("xhost -local:root -localhost>/dev/null 2>/dev/null")
				else:
					os.system("xhost -localhost >/dev/null 2>/dev/null")
			pprint("[green]=> Disabled X11 remote access.[/green]")
			verbose_print(
				f"[cyan]=> Bringing down container with ID: {pwnbox_container.short_id}[/cyan]"
			)
			pprint("[blue]=> Stopping PwnBox container...[/blue]")
			pwnbox_container.kill()
			pprint("[green]=> PwnBox container successfully stopped![/green]")
			sys_exit(0)
		except docker.errors.NotFound:
			pprint("[red]=> Error: PwnBox container not running. Exiting...[/red]")
			sys_exit(1)
	elif args.command == "pull":
		try:
			# Grab the local image
			pprint("[blue]=> Checking for local PwnBox image...[/blue]")
			local_image = client.images.get(
				f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}"
			)

			# Grab registry data
			with console.status(
				"[cyan]=> Checking for newer PwnBox images...[/cyan]", spinner="dots"
			):
				registry_data = client.images.get_registry_data(
					f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}"
				)

			if local_image.attrs["RepoDigests"][0].split("@")[1] == registry_data.id:
				pprint("[green]=> Already updated to latest version![/green]")
				sys_exit(0)
			else:
				pprint("[blue]=> A newer version of PwnBox has been found![/blue]")
		except docker.errors.ImageNotFound:
			pprint(
				"[yellow]=> PwnBox image not found locally, pulling image...[/yellow]"
			)
		except docker.errors.APIError:
			pprint("[red]=> There was an error contacting the Docker API.[/red]")
			sys_exit(1)

		# Download the latest image
		pull_progress = client.api.pull(
			f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox",
			tag=config["IMAGE"]["IMAGE_TAG"],
			stream=True,
			decode=True,
		)
		with Progress(
			"[progress.description]{task.description}",
			BarColumn(),
			"[progress.percentage]{task.percentage:>3.0f}%",
		) as progress:
			tasks = {}
			for _s in pull_progress:
				if "progressDetail" in _s:
					if _s["progressDetail"] != {}:
						if _s["id"] in tasks:
							if (
								_s["progressDetail"]["current"]
								== _s["progressDetail"]["total"]
							):
								progress.update(
									tasks[_s["id"]]["rich_task"],
									description=f"[dim green]Downloaded layer {_s['id']} [bold][{byte_to_human_read(_s['progressDetail']['total'])}][/bold][/dim green]",
									advance=(
										_s["progressDetail"]["current"]
										- tasks[_s["id"]]["progress"]["current"]
									),
								)
							else:
								progress.update(
									tasks[_s["id"]]["rich_task"],
									description=f"[dim {'blue' if _s['status'] == 'Downloading' else 'cyan'}]{_s['status']} layer {_s['id']} [bold][{byte_to_human_read(_s['progressDetail']['total'])}][/bold][/dim {'blue' if _s['status'] == 'Downloading' else 'cyan'}]",
									advance=(
										_s["progressDetail"]["current"]
										- tasks[_s["id"]]["progress"]["current"]
									),
								)
								tasks[_s["id"]]["progress"] = _s["progressDetail"]
						else:
							tasks[_s["id"]] = {}
							tasks[_s["id"]]["progress"] = _s["progressDetail"]
							tasks[_s["id"]]["rich_task"] = progress.add_task(
								f"[dim blue]{_s['status']} layer {_s['id']} [bold][{byte_to_human_read(_s['progressDetail']['total'])}][/bold][/dim blue]",
								total=_s["progressDetail"]["total"],
							)
							progress.update(
								tasks[_s["id"]]["rich_task"],
								advance=_s["progressDetail"]["current"],
							)
		pprint("[green]=> PwnBox image pulled/updated successfully!")
		sys_exit(0)
	elif args.command == "generate":
		if not os.path.isfile(args.config):
			conf_file = open(f"{os.path.dirname(__file__)}/pwnbox.conf", "r").read()
			open(args.config, "w").write(conf_file)
			pprint(f'[green]=> Generated a default config file at "{args.config}"!')
			sys_exit(0)
		else:
			pprint(f'[red]=> Error: "{args.config}" already exists![/red]')
			sys_exit(1)


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		pprint("[bold red]=> CTRL+C Received. Exiting...[/bold red]")
		sys_exit(0)
