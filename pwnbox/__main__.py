#!/usr/bin/env python
import argparse
import configparser
import math
import os
from sys import exit as ex
from sys import platform
from pathlib import Path

import docker
import requests
from packaging import version
from rich import print
from rich.console import Console
from rich.progress import BarColumn, Progress
from ssh_wait import ssh_wait

# Global Vars
VERSION = "v1.2.3"
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
def main():
	# Initialize ArgParser
	class NoAction(argparse.Action):
		def __init__(self, **kwargs):
			kwargs.setdefault('default', argparse.SUPPRESS)
			kwargs.setdefault('nargs', 0)
			super(NoAction, self).__init__(**kwargs)
		def __call__(self, parser, namespace, values, option_string=None):
			pass
	parser = argparse.ArgumentParser(description='Launch and manage PwnBox containers.')
	parser.register('action', 'none', NoAction)

	# Main arguments
	parser.add_argument('command', metavar='COMMAND', help='The action to perform.', choices=['up', 'down', 'pull', 'generate'])
	parser.add_argument('-v', '--verbose', help='Enable verbose output.', action='store_true')
	parser.add_argument('--version', help='Print the current version of the program.', action='version', version=f'{VERSION}')	
	parser.add_argument('-b', '--no-banner', help='Disable printing the banner.', action='store_true')
	parser.add_argument('-n', '--no-update', help='Disable the automatic check for newer PwnBox versions.', action='store_true')
	parser.add_argument('-c', '--config', help='Specify the path to a PwnBox config file.', default=f"{os.getenv('HOME')}/.pwnbox/pwnbox.conf")
	parser.add_argument('-t', '--timeout', help='Specify the timeout of waiting for SSH to be available.', type=int, default=10)

	# Possible commands
	group = parser.add_argument_group(title='Commands')
	group.add_argument('up', help='Starts the PwnBox container if not already started, and connects to it.', action='none')
	group.add_argument('down', help='Stop the PwnBox container.', action='none')
	group.add_argument('pull', help='Download the latest PwnBox image.', action='none')
	group.add_argument('generate', help='Write the default config to a file.', action='none')

	# Parse Args
	args = parser.parse_args()

	# Verbose printing function
	def verbose_print(s):
		if args.verbose:
			print(s)

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
		print(f'[red]{banner}[/red]')
		# Fancy small calculation to center the subtitle
		subtitle = f'[cyan]{VERSION}[/cyan] - Made by @DeadPackets'
		padding = len(banner.split('\n')[1])
		print(f'[blue]{subtitle.center(padding)}[/blue]\n')

	# Attempt to read the config file
	config = configparser.ConfigParser()
	args.config = os.path.expandvars(args.config)
	if args.command != 'generate':
		if os.path.isfile(args.config):
			try:
				config.read(args.config)
			except configparser.Error:
				print('[red]=> Error: Cannot read or parse config file!')
				exit(1)
		elif args.config == f"{os.getenv('HOME')}/.pwnbox/pwnbox.conf":
			print(f'[cyan]=> Creating default config at {args.config}')
			Path(args.config).parent.mkdir(exist_ok=True)
			f = open(f'{os.path.dirname(__file__)}/pwnbox.conf', 'r').read()
			open(args.config, 'w').write(f)
			config.read(args.config)
		else:
			print(f'[red]=> Error: "{args.config}" does not exist![/red]')
			exit(1)

	# Check if a newer version has been released
	if not args.no_update:
		try:
			git_version = requests.get('https://raw.githubusercontent.com/DeadPackets/pwnbox-cli/main/VERSION.txt').text.strip()
			if version.parse(git_version) > version.parse(VERSION):
				print(f'[cyan]=> A new version of PwnBox CLI ({git_version}) has been released. Upgrade to get the latest features and fixes.[/cyan]')
		except Exception:
			print('[red]=> Error: There was an error trying to check GitHub for the latest version.[/red]')

	# Test if we have access to docker
	try:
		client = docker.from_env()
	except docker.errors.DockerException:
		print('[red]=> Error: Could not connect to Docker. Check if Docker is running with proper permissions.[/red]')
		exit(1)

	# If the command is "UP"
	if args.command == 'up':
		# Check if the container is running
		try:
			pwnbox_container = client.containers.get(config['CONTAINER']['NAME'])
			print('[blue]=> PwnBox container already running! Logging in...[/blue]')
		except docker.errors.NotFound:
			# Test if we have the image downloaded
			container_image = f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}"
			print(f'[magenta]=> Image {container_image} selected...[/magenta]')
			try:
				print(f'[blue]=> Image already downloaded, continuing...[/blue]')
				# Grab local image
				local_image = client.images.get(container_image)

				# Grab registry data
				if not args.no_update:
					with console.status('[cyan]=> Checking for newer PwnBox images...[/cyan]', spinner='dots'):
						registry_data = client.images.get_registry_data(f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}")

					if local_image.short_id != registry_data.short_id:
						print('[yellow]=> A newer version of the PwnBox container is available! Run "pwnbox pull" to update.[/yellow]')
			except docker.errors.ImageNotFound:
				print('[yellow]=> PwnBox image not found locally, pulling image...[/yellow]')
				pull_progress = client.api.pull(f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox", tag=config['IMAGE']['IMAGE_TAG'], stream=True, decode=True)
				with Progress("[progress.description]{task.description}",BarColumn(),"[progress.percentage]{task.percentage:>3.0f}%") as progress:
					tasks = {}
					for s in pull_progress:
						if 'progressDetail' in s:
							if s['progressDetail'] != {}:
								if s['id'] in tasks:
									progress.update(tasks[s['id']]['rich_task'], advance=(s['progressDetail']['current'] - tasks[s['id']]['progress']['current']))
									tasks[s['id']]['progress'] = s['progressDetail']
								else:
									tasks[s['id']] = {}
									tasks[s['id']]['progress'] = s['progressDetail']
									tasks[s['id']]['rich_task'] = progress.add_task(f"Downloading layer {s['id']} [{byte_to_human_read(s['progressDetail']['total'])}]", total=s['progressDetail']['total'])
									progress.update(tasks[s['id']]['rich_task'], advance=s['progressDetail']['current'])
				print('[green]=> PwnBox image downloaded successfully![/green]')

			# Run the container
			try:
				# Prepare environment variables
				env_vars = {}
				if bool(config['CONTAINER']['X11_FORWARDING']):
					is_linux = (platform == 'linux' or platform == 'linux2')
					env_vars['DISPLAY'] = os.getenv('DISPLAY') if is_linux else 'host.docker.internal:0'
					with console.status('[cyan]=> Allowing X11 remote access...[/cyan]'):
						if is_linux:
							os.system('xhost +local:root >/dev/null 2>/dev/null')
						else:
							os.system('xhost +localhost >/dev/null 2>/dev/null')
					print('[blue]=> X11 remote access enabled.[/blue]')

				# Forward ports
				forwarded_ports = {}
				for part in config['CONTAINER']['FORWARDED_PORT'].split(','):
					# Okay this is gonna be sort of complex
					container_ports, host_ports = part.split(':')
					if '-' not in container_ports:
						forwarded_ports[f'{container_ports}/tcp'] = int(host_ports)
					else:
						container_port_range = range(int(container_ports.split('-')[0]), int(container_ports.split('-')[1])+1)
						host_port_range = range(int(host_ports.split('-')[0]), int(host_ports.split('-')[1])+1)
						if len(container_port_range) == len(host_port_range):
							for c, h in zip(container_port_range, host_port_range):
								forwarded_ports[f'{c}/tcp'] = h
						else:
							print(f'[red]=> Error: Invalid port mapping "{part}"! Exiting...[/red]')
							exit(1)

				# Volumes
				volume_config = {
						os.path.expandvars(config['CONTAINER']['EXTERNAL_VOLUME']): {
							'bind': '/mnt/external',
							'mode': 'rw'
						},
						os.path.expandvars(config['CONTAINER']['SSH_VOLUME']): {
							'bind': '/opt/ssh',
							'mode': 'ro'
						}
				}

				# Add X11 forwarding info on linux
				if is_linux:
					volume_config['/tmp/.X11-unix'] = {
						'bind': '/tmp/.X11-unix',
						'mode': 'rw'
					}

				container_id = client.containers.run(
					container_image,
					auto_remove=bool(config['CONTAINER']['AUTO_REMOVE']),
					detach=True,
					environment=env_vars,
					hostname=config['CONTAINER']['HOSTNAME'],
					ports=forwarded_ports,
					privileged=bool(config['CONTAINER']['PRIVILEGED']),
					remove=bool(config['CONTAINER']['AUTO_REMOVE']),
					name=config['CONTAINER']['NAME'],
					network_mode='host' if (bool(config['CONTAINER']['HOST_NETWORKING']) and is_linux) else 'bridge',
					volumes=volume_config
				)

				verbose_print(f'[cyan]=> Container has been launched with ID: {container_id.short_id}[/cyan]')
				print('[green]=> PwnBox launched successfully![/green]')
			except docker.errors.APIError:
				print('[red]=> Error: There was an error launching the PwnBox container. Exiting...')
				exit(1)

		# Wait for SSH
		with console.status('[blue]=> Waiting for SSH to be available...[/blue]', spinner='dots'):
			ssh_result = ssh_wait('127.0.0.1', service=2222, wait_limit=args.timeout*10, log_fn=None)
		if ssh_result == 0:
			# SSH into the container
			print('[green]=> SSH available! Logging in...[/green]')
			os.execlp('ssh', '-oStrictHostKeyChecking=no', 'root@127.0.0.1', '-p 2222')
		else:
			print('[red]=> Error: Timeout waiting for SSH to available in PwnBox.[/red]')
			exit(1)
	elif args.command == 'down':
		# Check if the container is running
		try:
			pwnbox_container = client.containers.get(config['CONTAINER']['NAME'])
			with console.status('[cyan]=> Disabling X11 remote access...[/cyan]'):
				if (platform == 'linux' or platform == 'linux2'):
					os.system('xhost -local:root >/dev/null 2>/dev/null')
				else:
					os.system('xhost -localhost >/dev/null 2>/dev/null')
			print('[green]=> Disabled X11 remote access.[/green]')
			verbose_print(f'[cyan]=> Bringing down container with ID: {pwnbox_container.short_id}[/cyan]')
			print('[blue]=> Stopping PwnBox container...[/blue]')
			pwnbox_container.kill()
			print('[green]=> PwnBox container successfully stopped![/green]')
			exit(0)
		except docker.errors.NotFound:
			print('[red]=> Error: PwnBox container not running. Exiting...[/red]')
			exit(1)
	elif args.command == 'pull':
		try:
			# Grab the local image
			print(f'[blue]=> Checking for local PwnBox image...[/blue]')
			local_image = client.images.get(f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}")

			# Grab registry data
			with console.status('[cyan]=> Checking for newer PwnBox images...[/cyan]', spinner='dots'):
				registry_data = client.images.get_registry_data(f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox:{config['IMAGE']['IMAGE_TAG']}")

			if local_image.short_id == registry_data.short_id:
				print('[green]=> Already updated to latest version![/green]')
				exit(0)
			else:
				print('[blue]=> A newer version of PwnBox has been found![/blue]')
		except docker.errors.ImageNotFound:
			print('[yellow]=> PwnBox image not found locally, pulling image...[/yellow]')
		except docker.errors.APIError:
			print('[red]=> There was an error contacting the Docker API.[/red]')
			exit(1)

		# Download the latest image
		pull_progress = client.api.pull(f"{config['IMAGE']['DOCKER_REPOSITORY']}/deadpackets/pwnbox", tag=config['IMAGE']['IMAGE_TAG'], stream=True, decode=True)
		with Progress("[progress.description]{task.description}",BarColumn(),"[progress.percentage]{task.percentage:>3.0f}%") as progress:
			tasks = {}
			for s in pull_progress:
				if 'progressDetail' in s:
					if s['progressDetail'] != {}:
						if s['id'] in tasks:
							progress.update(tasks[s['id']]['rich_task'], advance=(s['progressDetail']['current'] - tasks[s['id']]['progress']['current']))
							tasks[s['id']]['progress'] = s['progressDetail']
						else:
							tasks[s['id']] = {}
							tasks[s['id']]['progress'] = s['progressDetail']
							tasks[s['id']]['rich_task'] = progress.add_task(f"Downloading layer {s['id']} [{byte_to_human_read(s['progressDetail']['total'])}]", total=s['progressDetail']['total'])
							progress.update(tasks[s['id']]['rich_task'], advance=s['progressDetail']['current'])
		print('[green]=> PwnBox image pulled/updated successfully!')
		exit(0)
	elif args.command == 'generate':
		if not os.path.isfile(args.config):
			f = open(f'{os.path.dirname(__file__)}/pwnbox.conf', 'r').read()
			open(args.config, 'w').write(f)
			print(f'[green]=> Generated a default config file at "{args.config}"!')
			exit(0)
		else:
			print(f'[red]=> Error: "{args.config}" already exists![/red]')
			exit(1)

if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt:
		print('[bold red]=> CTRL+C Received. Exiting...[/bold red]')
		try:
			ex(0)
		except SystemExit:
			os._exit(0)
