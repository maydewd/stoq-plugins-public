from setuptools import setup, find_packages

setup(
    name="redis",
    version="0.2.1",
    author="Marcus LaFerrera (@mlaferrera)",
    url="https://github.com/PUNCH-Cyber/stoq-plugins-public",
    license="Apache License 2.0",
    description="Publish and Consume messages from a Redis Server",
    packages=find_packages(),
    include_package_data=True,
)
