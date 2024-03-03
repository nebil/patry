"""
utils.py
--------
This module has utility functions for formatting and manipulating money.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import overload

import httpx

from patry import SETTINGS


# fmt: off
@overload
def clean_money(number: str) -> float: ...
@overload
def clean_money(number: list[str]) -> list[float]: ...
# fmt: on
def clean_money(number):
    """
    Clean a string (or a list of them) representing monetary values from Chile.

    >>> clean_money("$1.234")
    1234.0
    >>> clean_money("10.000")
    10000.0
    >>> clean_money(" $31.415 ")
    31415.0
    >>> clean_money(" $ 1_234 ")
    1234.0
    >>> clean_money("$1.234,56")
    1234.56
    >>> clean_money(["$1.234", "10.000", " $31.415 "])
    [1234.0, 10000.0, 31415.0]

    Note: Do not confuse with money laundering.
    """

    def _clean(number: str) -> float:
        return float(number.replace(".", "").replace(",", ".").replace("$", ""))

    return _clean(number) if isinstance(number, str) else [_clean(n) for n in number]


def fetch_usd_clp(isodate: str | None = None) -> float | None:
    """
    Fetch the USD/CLP exchange rate for a given date using the API of "mindicador.cl".
    If `isodate` is not provided, it will fetch the exchange rate of `SETTINGS.today`.

    >>> fetch_usd_clp("2023-01-30")
    803.14
    """

    date_ = datetime.fromisoformat(isodate) if isodate else SETTINGS.today
    api_url = "https://mindicador.cl/api/dolar/" + date_.strftime("%d-%m-%Y")

    try:
        data = httpx.get(api_url).json()
        return data["serie"][0]["valor"]
    except Exception:
        logging.exception("Couldn't fetch exchange rate.")
        return None


class RichFormatter(logging.Formatter):
    """
    This Rich-powered custom formatter improves the visibility of command-line options
    (e.g. --option-name) by applying *bold* formatting to them within the log messages.
    """

    def format(self, record: logging.LogRecord) -> str:
        record.msg = re.sub(r"(--[\w-]+)", r"[bold]\1[/bold]", str(record.msg))
        return super().format(record)
