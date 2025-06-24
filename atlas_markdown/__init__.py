"""Atlas Markdown - Convert Atlassian documentation to Markdown."""

try:
    # Try to get version from setuptools_scm
    from ._version import version as __version__
except ImportError:
    # Fallback to static version
    __version__ = "0.1.1"

__all__ = ["__version__"]
