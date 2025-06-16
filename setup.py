#!/usr/bin/env python
"""
Setup script for Atlas Markdown

This is a minimal setup.py that delegates to setuptools and pyproject.toml
"""

from setuptools import find_packages, setup

setup(packages=find_packages(include=["atlas_markdown", "atlas_markdown.*"]))
