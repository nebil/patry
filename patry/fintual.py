"""
fintual.py
----------
This module works with Fintual.
"""

import asyncio
import itertools
import logging
import os
from collections.abc import AsyncIterator, Iterator
from datetime import date, datetime, timezone
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import IO, Any

import httpx

from patry import SETTINGS
from patry.asset import Asset, Cashflow, Portfolio
from patry.utils import clean_money

API_BASE_URL = "https://fintual.cl/api"
APP_BASE_URL = "https://fintual.cl/app"
FINTUAL_EMAIL = os.environ["FINTUAL_EMAIL"]
FINTUAL_TOKEN = os.environ["FINTUAL_TOKEN"]
FINTUAL_COOKIE = os.environ["FINTUAL_COOKIE"]

user_token = {"user_email": FINTUAL_EMAIL, "user_token": FINTUAL_TOKEN}
session_cookie = {"_fintual_session_cookie": FINTUAL_COOKIE}

FINTUAL_DATE_FORMAT = "%d/%m/%y"

# data = {"user": {"email": FINTUAL_EMAIL, "password": FINTUAL_PASSWORD}}
# token = httpx.post(API_BASE_URL + "/access_tokens", json=data)


async def fetch_data() -> Portfolio:
    """
    !>> import asyncio
    !>> asyncio.run(fetch_data())
    """

    def link(id_: int, name: str) -> str:
        """
        >>> link(1234, "My goal")
        '[link=https://fintual.cl/app/goals/1234]My goal[/link]'
        """

        return f"[link={APP_BASE_URL}/goals/{id_}]{name}[/link]"

    def create_asset(goal_id: int, attrs: dict[str, Any]) -> Asset:
        return Asset(
            # Read all cashflows from file; if unavailable, then use a dummy cashflow.
            list(read_patry(goal_id)) or [Cashflow(date.today(), attrs["deposited"])],
            int(attrs["nav"]),
            link(goal_id, attrs["name"]),
        )

    async with httpx.AsyncClient() as client:
        response = await client.get(API_BASE_URL + "/goals", params=user_token)

    logging.debug(goals := response.json()["data"])
    assets = [create_asset(g["id"], attrs) for g in goals if (attrs := g.get("attributes"))]
    return assets, [flow for asset in assets for flow in asset.cashflows]


async def write_patry_for_goals() -> None:
    """
    Write a cashflow file corresponding per Fintual goal.

    !>> import asyncio
    !>> asyncio.run(write_patry_for_goals())
    """

    async def fetch_and_write(goal_id: int) -> None:
        """
        Fetch and write cashflows of a single goal, asynchronously!
        """

        cashflows = [cf async for cf in _fetch_movements(goal_id)]
        with _open_patry("cashflows", goal_id, mode="w") as file:
            file.writelines(f"{cf.asline()}\n" for cf in reversed(cashflows))

    response = httpx.get(API_BASE_URL + "/goals", params=user_token)
    goal_ids = [int(goal["id"]) for goal in response.json()["data"]]
    await asyncio.gather(*(fetch_and_write(goal_id) for goal_id in goal_ids))


# AUXILIARY FUNCTIONS
# ========= =========


def get_available_patry(dirname: str) -> Iterator[int]:
    for filepath in Path(dirname).glob("fintual-*.patry"):
        _, goal_id = filepath.stem.split("-")
        yield int(goal_id)


def _open_patry(dirname: str, goal_id: int, *, mode: str = "r") -> IO[str]:
    """
    Open a .patry file corresponding to the specified Fintual goal.
    Note: This function can support both read and write operations.
    """

    folder = Path(dirname)
    folder.mkdir(exist_ok=True)
    filepath = folder / f"fintual-{goal_id}.patry"
    return open(filepath, mode, encoding="locale")  # noqa: SIM115


def read_patry(goal_id: int) -> Iterator[Cashflow]:
    """
    Read a cashflow file corresponding to the specified Fintual goal.
    """

    try:
        with _open_patry("cashflows", goal_id) as file:
            for line in file:
                date_, _ = line.split(",")
                if date_ > str(SETTINGS.today):
                    break
                yield Cashflow.fromline(line)

    except FileNotFoundError:
        logging.warning("Couldn't find file for goal (id=%s)", goal_id)
        return iter(())


def read_historical(goal_id: int) -> tuple[int, int] | tuple[None, None]:
    with _open_patry("historical", goal_id) as file:
        for line in file:
            date_, value1, value2 = line.split(",")
            if date_ == str(SETTINGS.today):
                return int(value1), int(value2)
        return None, None


async def _fetch_movements(goal_id: int) -> AsyncIterator[Cashflow]:
    """
    Fetch movements from a specific Fintual goal using a cookie-based auth, asynchronously!
    """

    async def single_page_fetch(page: int) -> list[dict[str, Any]]:
        url = f"{APP_BASE_URL}/goals/{goal_id}/movements"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, cookies=session_cookie, params={"page": page})

        try:
            return response.json()["data"]
        except JSONDecodeError:
            logging.exception("Oops!")
            return []

    # Let's fetch movements page by page!
    for page in itertools.count(start=1):
        logging.info("Fetching data from (goal_id=%s, page=%s)", goal_id, page)
        if not (movements := await single_page_fetch(page)):
            return

        for movement in movements:
            if attrs := movement.get("attributes"):
                date_ = datetime.strptime(attrs["created_at"], FINTUAL_DATE_FORMAT).date()
                amount = (1 if attrs["positive"] else -1) * clean_money(attrs["amount"])
                yield Cashflow(date_, amount)


def _fetch_historical(goal_id: int) -> None:
    """
    Fetch the historical performance from a specific Fintual goal using a cookie-based auth.
    """

    def _parse_datum(timestamp: int, value1: float, value2: float) -> str:
        date_ = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date()
        return f"{date_},{round(value1):_},{round(value2):_}\n"

    url = f"{APP_BASE_URL}/goals/{goal_id}/performance"
    try:
        response = httpx.get(url, cookies=session_cookie)
        performance = response.json()["data"]["attributes"]["performance"]
        data0 = performance[0]["data"]
        data1 = performance[1]["data"]
    except Exception:
        logging.exception("Oops!")
    else:
        with _open_patry("historical", goal_id, mode="w") as file:
            for d0, d1 in zip(data0, data1, strict=True):
                file.write(_parse_datum(d0["date"], d0["value"], d1["value"]))
