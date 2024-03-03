"""
__main__.py -- The entrypoint to this program.

Usage: Run `patry --help` to see all available commands and options.
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
from collections.abc import Iterable
from datetime import date
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile

from rich.box import MINIMAL
from rich.console import Console
from rich.logging import RichHandler

from patry import SETTINGS
from patry.asset import Asset, AssetTable, Portfolio
from patry.utils import RichFormatter, fetch_usd_clp

ACCOUNTS = ["bchile", "fintual", "renta4", "extras", "monio"]


def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    """
    Parse the command-line arguments provided by the user.
    """

    class HelpFormatter(argparse.HelpFormatter):
        # This custom class exists only to adjust the "max_help_position" argument.
        def __init__(self, *args, **kwargs) -> None:
            kwargs["max_help_position"] = 40
            super().__init__(*args, **kwargs)

    parser = argparse.ArgumentParser(
        description="Patry: a command-line interface for monitoring [my] financial assets.",
        epilog="More info at <https://github.com/nebil/patry>",
        formatter_class=HelpFormatter,
        add_help=False,
    )
    parser.add_argument(
        "accounts",
        nargs="+",
        choices=ACCOUNTS,
        metavar=f"<{'|'.join(ACCOUNTS)}>",
        help="Select the account(s) to check.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Fetch cashflows and store them.",
    )
    parser.add_argument(
        "--with-usd",
        nargs="?",
        type=int,
        const=3,
        dest="usdindex",
        metavar="COLINDEX",
        help="Include an extra column for USD.",
    )
    parser.add_argument(
        "--loaddata",
        type=date.fromisoformat,
        dest="today",
        metavar="YYYY-MM-DD",
        help="Load historical data from date.",
    )
    parser.add_argument(
        "--savejson",
        nargs="?",
        const="output.json",
        metavar="FILENAME",
        help="Export portfolio to a JSON file.",
    )
    parser.add_argument(
        "--headed",
        action="store_false",
        dest="headless",
        help="Show browser UI during execution.",
    )
    parser.add_argument(
        "--verbose",
        "--info",
        action="store_const",
        const=logging.INFO,
        dest="info",
        help="Set log level at <logging.INFO>.",
    )
    parser.add_argument(
        "--debug",
        action="store_const",
        const=logging.DEBUG,
        help="Set log level at <logging.DEBUG>.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=version(__package__),
        help="Show Patry's version and exit.",
    )
    parser.add_argument(
        "--help",
        action="help",
        help="Display this help message and exit.",
    )

    # If no argument is given, this will print the help message.
    # Calling "patry" is basically equivalent to "patry --help".
    return parser, parser.parse_args(sys.argv[1:] or ["--help"])


def print_table(accounts: Iterable[str], portfolio: Iterable[Portfolio]) -> AssetTable:
    """
    Print a Rich-powered table containing all assets.
    """

    table = AssetTable(box=MINIMAL)
    for account, (assets, cashflows) in zip(accounts, portfolio, strict=True):
        value = sum(asset.value for asset in assets)
        table.rows_.append(table.Subtotal(cashflows, value, f"Σ {account.upper()}"))
        table.rows_.extend(assets)
        table.rows_.append(table.Section())
        table.cashflows.extend(cashflows)

    table.compute()
    Console().print(table)
    return table


def save_file(new_data: dict[str, dict[str, int]]) -> None:
    """
    Save the subtotal of assets into a JSON file.
    Also, append new data under the current date.
    """

    try:
        with open(SETTINGS.savejson, encoding="locale") as file:
            data = json.load(file)
    # If the file doesn't exist or is empty... dict()
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    today = str(date.today())
    data |= {today: new_data}

    with NamedTemporaryFile("w", encoding="locale", delete=False) as tempfile:
        json.dump(data, tempfile, indent=4)

    logging.info("Writing file for: %s", today)
    shutil.move(tempfile.name, SETTINGS.savejson)


async def main() -> None:  # noqa: C901, PLR0912
    """
    Run the main execution flow of the program: logging setup, data fetching & output generation.
    """

    parser, args = parse_args()

    # --debug/--verbose
    loglevel = args.debug or args.info or logging.WARNING
    handler = RichHandler(markup=True)
    handler.setFormatter(RichFormatter(fmt="%(message)s", datefmt="%X"))

    logging.basicConfig(level=loglevel, handlers=[handler])
    logging.debug(args)
    logging.debug("The logging level was set to '%s'.", logging._levelToName[loglevel])

    # --loaddata/--headed/--savejson/--with-usd
    SETTINGS.today = args.today if args.today and args.today < date.today() else date.today()
    SETTINGS.headless = args.headless
    SETTINGS.savejson = args.savejson
    SETTINGS.usdindex = args.usdindex
    SETTINGS.usdtoclp = args.usdindex is not None and fetch_usd_clp()
    logging.info(SETTINGS)

    # Check .env file.
    if not Path(".env").exists():
        logging.error("[b].env[/b] file is missing. Please create one.")
        return

    # Executing "patry monio" will fetch the accounts defined in "MONIO", an environment variable.
    # If that variable is unset or empty, it defaults to fetching data for all supported accounts.
    if "monio" in args.accounts:
        monio = (_monio := os.getenv("MONIO")) and (s.lower().strip() for s in _monio.split(","))
        args.accounts = monio or ACCOUNTS[:-1]

    # Remove duplicates while preserving order by using "dict.fromkeys".
    accounts = dict.fromkeys(args.accounts)
    logging.info("Selected accounts: %s", ", ".join(accounts))

    # Delay importing account-specific modules (e.g. renta4) until required by the execution flow.
    # This should optimize startup time and memory usage by loading dependencies only when needed.
    from patry import fintual, renta4  # noqa: PLC0415

    # --loaddata
    if args.today:
        # TODO: This currently only works with Fintual. Make it work with other accounts.
        if list(accounts) != ["fintual"]:
            parser.error("This only works with Fintual.")

        if args.no_cache or args.headless or args.savejson:
            logging.warning("If --loaddata is used, --headed/--no-cache/--savejson are ignored.")

        data = [
            # Each element should be structured as: (cashflows, deposited, value)
            (list(fintual.read_patry(goal_id)), *fintual.read_historical(goal_id))
            for goal_id in fintual.get_available_patry("historical")
        ]

        assets = [Asset(cashflows, value) for cashflows, _, value in data]
        cashflows = [flow for asset in assets for flow in asset.cashflows]

        # These lines might fix eventual inconsistencies between files.
        for (_, deposited, _), asset in zip(data, assets, strict=True):
            if deposited and asset.outlay != deposited:
                logging.info("Last cashflow removed!")
                asset.cashflows = asset.cashflows[:-1]

        print_table(accounts, [(assets, cashflows)])
        return

    # --no-cache
    # If enabled, create all cashflow files for each account if possible.
    if args.no_cache:
        if "bchile" in accounts:
            logging.warning("--no-cache doesn't work for Banco de Chile.")
        if "fintual" in accounts:
            await fintual.write_patry_for_goals()
        if "renta4" in accounts:
            await renta4.write_patry()
            await renta4.write_patry_for_stocks()
        if "extras" in accounts:
            logging.warning("--no-cache doesn't work for AFP Modelo yet.")

    # For each account, fetch all data asynchronously.
    tasks = (import_module(f"patry.{account}").fetch_data() for account in accounts)
    table = print_table(accounts, await asyncio.gather(*tasks))

    # --savejson
    if args.savejson:
        subtotals = (row for row in table.rows_ if isinstance(row, AssetTable.Subtotal))
        save_file(
            {
                account: {"outlay": subtotal.outlay, "market": subtotal.value}
                for account, subtotal in zip(accounts, subtotals, strict=True)
            }
        )


def entrypoint() -> None:
    """
    A sync entrypoint for Poetry.
    """

    asyncio.run(main())
