#!/usr/bin/env python3

import os
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="har2requests",
    version="0.1.1",
    author="Louis Abraham",
    license="MIT",
    author_email="louis.abraham@yahoo.fr",
    description="Generate Python Requests code from HAR file",
    long_description=read("README.rst"),
    url="https://github.com/louisabraham/har2requests",
    packages=["har2requests"],
    install_requires=["black", "click"],
    python_requires=">=3.6",
    entry_points={"console_scripts": ["har2requests = har2requests:main"]},
    classifiers=[
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",
    ],
)
