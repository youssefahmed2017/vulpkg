"""Setup script for vulp."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="vulp",
    version="0.1.0",
    author="stefand-0",
    author_email="stefan.dragan95@gmail.com",
    description="Package manager for the Vulpin programming language",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/stefand-0/vulp",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    install_requires=[
        "packaging>=21.0",
        "tomli>=2.0.0; python_version<'3.11'",
        "tomli-w>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "vulp=vulp.cli:main",
        ],
    },
)
