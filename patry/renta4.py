"""
renta4.py
---------
This module works with Renta4.
"""

import logging
import os
from collections.abc import Callable
from datetime import date, datetime
from functools import wraps
from itertools import count, groupby
from operator import itemgetter
from pathlib import Path
from typing import IO, Any, Concatenate, ParamSpec

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import async_playwright as playwright

from patry import SETTINGS
from patry.asset import Asset, Cashflow, Portfolio
from patry.utils import clean_money

BASE_URL = "https://webprivate.renta4.cl/www/"
LOGIN_URL = BASE_URL + "login.html"
STOCKS_URL = BASE_URL + "crentavariable.html"
DETAILS_URL = BASE_URL + "detalletransacciones.html"
MOVEMENTS_URL = BASE_URL + "movimientosperiodo.html"

CHILE_ID_NUMBER = os.environ["CHILE_ID_NUMBER"]
RENTA4_PASSWORD = os.environ["RENTA4_PASSWORD"]
RENTA4_START_DATE = date.fromisoformat(os.environ["RENTA4_START_DATE"])
RENTA4_DATE_FORMAT = "%d-%m-%Y"

Param = ParamSpec("Param")


def logged_in(action: Callable[Concatenate[Page, Param], Any]) -> Callable[Param, Any]:
    """
    Use this decorator to log in to Renta4 website.
    """

    async def login(page: Page) -> Page:
        """
        Log in to Renta4 and that's it.
        """

        logging.info("Logging in to Renta4.")
        await page.goto(BASE_URL)
        await page.locator("#rut").fill(CHILE_ID_NUMBER)
        await page.locator("#password").fill(RENTA4_PASSWORD)
        await page.locator("input[type=submit]").click()
        return page

    @wraps(action)
    async def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> Any:  # noqa: ANN401
        async with playwright() as play:
            browser = await play.firefox.launch(headless=SETTINGS.headless)
            page = await browser.new_page()

            try:
                return await action(await login(page), *args, **kwargs)
            except PlaywrightError:
                logging.exception("Oops!")
            finally:
                logging.info("Logging out from Renta4.")
                await browser.close()

    return wrapper


@logged_in
async def fetch_data(page: Page) -> Portfolio:  # noqa: PLR0914
    """
    !>> import asyncio
    !>> asyncio.run(fetch_data())
    """

    def link(name: str) -> str:
        """
        >>> link("CHILE")
        '[link=https://webprivate.renta4.cl/www/venta.html?idInstrument=CHILE]CHILE[/link]'
        """

        return f"[link={BASE_URL}venta.html?idInstrument={name}]{name}[/link]"

    try:
        # Balance
        assets = page.get_by_text("Patrimonio por Instrumentos")
        parent = page.locator("div.card").filter(has=assets)
        names_ = parent.locator("th a")
        await names_.first.wait_for()
        names = [name.strip() for name in await names_.all_text_contents()]
        values = clean_money(await parent.locator("td:nth-child(2)").all_text_contents())

        # Chilean stocks
        await page.goto(STOCKS_URL)
        chile = page.locator("div#pills-chile")
        await chile.wait_for()
        tickers = [tick.strip() for tick in await chile.locator("th a").all_text_contents()]
        *initial, tinit = clean_money(await chile.locator("td:nth-child(4)").all_text_contents())
        *current, _curr = clean_money(await chile.locator("td:nth-child(6)").all_text_contents())

    except PlaywrightError:
        logging.exception("Oops! Couldn't fetch the data.")
        return [], []

    else:
        mapping = dict(zip(names, values, strict=True))
        valcash = mapping.get(keycash := "Disponible", 0)
        valfunds = mapping.get(keyfunds := "Fondos Mutuos", 0)

        cashflows = _read_patry("")
        # Determining the total invested amount in mutual funds is not straightforward.
        # This is why we alternatively calculate a "delta" value by subsracting
        # the amounts in stocks and cash from the total of historical cashflows.
        # However, if cashflows are not available, "delta" will simply default to zero.
        delta = sum(flow.amount for flow in cashflows) - tinit - valcash if cashflows else 0

        cash = Asset(name=keycash, flows=[Cashflow(today := date.today(), valcash)])
        funds = Asset(name=keyfunds, flows=[Cashflow(today, delta)], value=valfunds)
        stocks = (
            Asset(name=link(tick), flows=_read_patry(tick) or [Cashflow(today, init)], value=curr)
            for tick, init, curr in zip(tickers, initial, current, strict=True)
        )

        return [cash, funds, *stocks], cashflows


async def write_patry() -> None:
    """
    Fetch all deposits made to Renta4.

    !>> import asyncio
    !>> asyncio.run(write_patry())
    """

    if deposits := await _get_events_by_name("Abono en dinero"):
        cashflows = (Cashflow(date_, amount) for date_, _, amount in reversed(deposits))

        with _open_patry("", "w") as file:
            file.writelines(f"{cf.asline()}\n" for cf in cashflows)


@logged_in
async def write_patry_for_stocks(page: Page) -> None:
    """
    Fetch all purchase information for all transacted stocks.

    !>> import asyncio
    !>> asyncio.run(write_patry_for_stocks())
    """

    try:
        await page.goto(DETAILS_URL)
        select = page.locator("select#custodiaInstrumento")

        # Get all options/tickers
        options = await select.locator("option").all()
        tickers = [value for option in options if (value := await option.get_attribute("value"))]

        # Select the initial date
        # The "fill()-then-type()" is required to trigger events on jQuery's date picker.
        await page.fill("input#fechaIni", "")
        await page.type("input#fechaIni", RENTA4_START_DATE.strftime(RENTA4_DATE_FORMAT))

        for ticker in tickers:
            await select.select_option(ticker)
            await page.get_by_role("button", name="Ir").click()
            table = page.locator("div.table-responsive")
            await table.wait_for()

            # Fetch info from table (date, volume, price) and group by date (that's index=0)
            grouped = groupby(
                zip(
                    await table.locator("td:nth-child(1)").all_text_contents(),
                    clean_money(await table.locator("td:nth-child(4)").all_text_contents()),
                    clean_money(await table.locator("td:nth-child(5)").all_text_contents()),
                    strict=True,
                ),
                key=itemgetter(0),
            )

            # Generate a sequence of cashflows
            cashflows = (
                Cashflow(
                    purchase_date=datetime.strptime(date_, RENTA4_DATE_FORMAT).date(),
                    amount=sum((volume * price) for _, volume, price in group),
                )
                for date_, group in grouped
            )

            # Finally, write the cashflow file
            logging.info("Writing file for ticker=%s", ticker)
            with _open_patry(ticker, "w") as file:
                file.writelines(f"{cf.asline()}\n" for cf in cashflows)

    except PlaywrightError:
        logging.exception("Oops! Couldn't get all transactions.")


# AUXILIARY FUNCTIONS
# ========= =========


def _open_patry(ticker: str = "", mode: str = "r") -> IO[str]:
    """
    Open a cashflow file corresponding to the specified Renta4 ticker.
    If no ticker is provided, the renta4.patry will be opened instead.
    """

    folder = Path("cashflows")
    folder.mkdir(exist_ok=True)
    filestem = ticker and "-" + ticker.lower()
    filepath = folder / f"renta4{filestem}.patry"
    return open(filepath, mode, encoding="locale")  # noqa: SIM115


def _read_patry(ticker: str) -> list[Cashflow]:
    try:
        with _open_patry(ticker) as file:
            return [Cashflow.fromline(line) for line in file]

    except FileNotFoundError:
        logging.warning("Couldn't find file for ticker (name=%s)", ticker)
        return []


@logged_in
async def _get_all_stocks(page: Page) -> list[str] | None:
    """
    Fetch the tickers of all available stocks.

    !>> import asyncio
    !>> asyncio.run(_get_all_stocks())
    """

    try:
        stocks_ = page.locator("div#custodia table")
        await stocks_.wait_for()
        stocks = await stocks_.locator("td:nth-child(2)").all_text_contents()
        return [text.strip() for text in stocks]

    except PlaywrightError:
        logging.exception("Oops! Couldn't get all stocks.")
        return None


@logged_in
async def _get_events_by_name(page: Page, event_name: str) -> list[tuple[date, str, float]] | None:
    """
    Fetch all the events by string.

    !>> import asyncio
    !>> asyncio.run(_get_events_by_name("Abono en dinero"))
    """

    data: list[tuple[date, str, float]] = []

    try:
        await page.goto(MOVEMENTS_URL)
        await page.fill("input#fechaIni", "")
        await page.type("input#fechaIni", RENTA4_START_DATE.strftime(RENTA4_DATE_FORMAT))
        await page.get_by_role("button", name="Buscar").click()

        for _page in count(start=1):
            logging.info("Fetching data from page=%s", _page)
            table = page.locator("div.table-responsive")
            await table.wait_for()

            # Fetch info from table: dates (1), event names (2), amounts (6)
            dates = await table.locator("td:nth-child(1)").all_text_contents()
            names = await table.locator("td:nth-child(2)").all_text_contents()
            amounts = await table.locator("td:nth-child(6)").all_text_contents()

            data.extend(
                (datetime.strptime(date_, RENTA4_DATE_FORMAT).date(), name, clean_money(amount))
                for date_, name, amount in zip(dates, names, amounts, strict=True)
                if name.upper() == event_name.upper()
            )

            next_button = page.locator("li.next a")
            if await next_button.count() == 0:
                break
            await next_button.click()

    except PlaywrightError:
        logging.exception("Oops! Couldn't get all events.")
        return None
    else:
        return data
