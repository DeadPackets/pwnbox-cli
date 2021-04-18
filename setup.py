import setuptools
from os import path
import pathlib

# GLOBALS
VERSION = "v1.2.3"
HERE = pathlib.Path(__file__).parent
README = open(f'{HERE}/README.md', 'r').read()
with open(path.join(HERE, 'requirements.txt'), encoding='utf-8') as f:
    all_reqs = f.read().split('\n')
install_requires = [x.strip() for x in all_reqs if ('git+' not in x) and (not x.startswith('#')) and (not x.startswith('-'))]
dependency_links = [x.strip().replace('git+', '') for x in all_reqs if 'git+' not in x]

setuptools.setup(
	name='pwnbox',
	version=VERSION,
	python_requires='>=3.6',
	url='https://github.com/deadpackets/pwnbox-cli',
	author='DeadPackets (Youssef Awad)',
	author_email='deadpackets@protonmail.com',
	description='The CLI tool that lets you easily deploy, customize and manage PwnBox containers.',
	long_description=README,
	long_description_content_type='text/markdown',
	entry_points='''
		[console_scripts]
		pwnbox=pwnbox.__main__:main
	''',
	keywords='pwnbox, kali, container, docker, security, pentesting',
	packages=setuptools.find_packages(),
	license='MIT',
	install_requires=install_requires,
	dependency_links=dependency_links,
	include_package_data=True,
	package_data={
		"": ["*.conf"]
	},
	classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
	]
)