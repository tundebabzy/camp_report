from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in camp_report/__init__.py
from camp_report import __version__ as version

setup(
	name="camp_report",
	version=version,
	description="Custom reports for Camp Company",
	author="tundebabzy@gmail.com",
	author_email="tundebabzy@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
