"""Core package for the Avarr downloader service."""

from importlib.metadata import version, PackageNotFoundError


def get_version() -> str:
    """Return the installed package version or a dev placeholder."""

    try:
        return version("avarr")
    except PackageNotFoundError:
        return "0.0.0-dev"


__all__ = ["get_version"]
