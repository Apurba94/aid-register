"""Start the app: python -m aid_register [data.db] [--port 8031]"""
import sys

from .fieldkit import main_cli
from .web import create_app

sys.exit(main_cli(create_app, "aid.db", 8031, sys.argv))
