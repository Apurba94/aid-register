"""Aid Register: an offline beneficiary and distribution register."""
from . import core
from .web import create_app

__all__ = ["core", "create_app"]
