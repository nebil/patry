# This __init__.py file only exists to avert the following mypy error:
# error: Source file found twice under different module names: "<file>" and "patry.<file>"
# Check: https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-paths-to-modules

from datetime import date
from types import SimpleNamespace

from dotenv import load_dotenv

# The "SimpleNamespace" class is preferred (over a dictionary) for enabling easier access
# to the settings via dot notation.
SETTINGS = SimpleNamespace(
    headless=False,
    savejson=None,
    usdindex=None,
    usdtoclp=None,
    today=date.today(),
)

load_dotenv()
