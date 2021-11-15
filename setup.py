import os
import re
from codecs import open

from setuptools import find_packages, setup

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()
long_description_content_type = "text/markdown"

VERSION = "1.0.0"

setup(
    name="ipd",
    version=VERSION,
    description="An IPD - Image Push and Deploy",
    long_description=long_description,
    long_description_content_type=long_description_content_type,
    url="https://github.com/13hakta/ipd/",
    author="Vitaly Chekryzhev",
    author_email="13hakta@gmail.com",
    license="Proprietary",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: System :: Networking :: Monitoring",
        "Typing :: Typed",
    ],
    project_urls={
        "Source": "https://github.com/13hakta/ipd/",
    },
    packages=find_packages(
        include=[
            "ipd",
            "ipd.*",
        ]
    ),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "ipd = ipd.ipd:main",
        ]
    },
    python_requires=">=3.6",
    install_requires=[
        "flask",
        "waitress",
    ],
    extras_require={
        "dev": [],
    },
)
