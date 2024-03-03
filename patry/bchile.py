"""
bchile.py
---------
This module works with Banco de Chile.
"""

import logging
import os
from datetime import date, datetime

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright as playwright

from patry import SETTINGS
from patry.asset import Asset, Cashflow, Portfolio
from patry.utils import clean_money

LOGIN_URL = "https://login.portal.bancochile.cl"
TIME_DEPOSIT_URL = "https://portalpersonas.bancochile.cl/mibancochile-web/front/persona/index.html#/dap-consulta/consultar"
CHILE_ID_NUMBER = os.environ["CHILE_ID_NUMBER"]
BCHILE_PASSWORD = os.environ["BCHILE_PASSWORD"]
BCHILE_FILEPATH = "cashflows/bchile.patry"
BCHILE_DATE_FORMAT = "%d/%m/%Y"


def _blank_deposit(isodate: str) -> Asset:
    """
    >>> str(_blank_deposit("1970-01-01"))
    '(DAP [1970-01-01]) $0->$0'
    """

    return Asset(name=f"DAP [{isodate}]", flows=[])


def _parse_deposit(line: str) -> tuple[str, Asset]:
    """
    >>> isodate, asset = _parse_deposit("2023-01-30,1_000_000")
    >>> isodate, str(asset)
    ('2023-01-30', '(DAP [2023-01-30]) $1.000.000->$1.000.000')
    """

    asset = _blank_deposit(isodate := line.split(",")[0])
    asset.cashflows.append(Cashflow.fromline(line))
    return isodate, asset


async def fetch_data() -> Portfolio:
    """
    !>> import asyncio
    !>> asyncio.run(fetch_data())
    """

    async with playwright() as play:
        browser = await play.firefox.launch(headless=SETTINGS.headless)
        page = await browser.new_page()

        try:
            # Log in
            logging.info("Logging in to Banco de Chile.")
            await page.goto(LOGIN_URL)
            await page.get_by_placeholder("Rut Usuario").fill(CHILE_ID_NUMBER)
            await page.get_by_placeholder("Clave").fill(BCHILE_PASSWORD)
            await page.locator("button#idIngresar").click()

            # Get account balance
            logging.info("Fetching the account balance.")
            content = await page.locator("span.monto-cuenta").first.text_content() or "$0"
            balance = clean_money(content)

            # Get all time deposits
            logging.info("Fetching the time deposits.")
            await page.goto(TIME_DEPOSIT_URL)
            amounts_loc = page.locator("td.bch-column-montoVencimiento")
            await amounts_loc.first.wait_for()
            dates = await page.locator("td.bch-column-fechaInicialFormato").all_text_contents()
            amounts = await amounts_loc.all_text_contents()

        except PlaywrightError:
            logging.exception("Oops!")
            return [], []

        else:
            # Merge to information on time deposit file
            try:
                with open(BCHILE_FILEPATH, encoding="locale") as file:
                    deposits = dict(map(_parse_deposit, file))
            except FileNotFoundError:
                logging.warning("Couldn't find file for time deposits.")
                deposits = {}

            for date_, amount in zip(dates, amounts, strict=True):
                isodate = datetime.strptime(date_.strip(), BCHILE_DATE_FORMAT).strftime("%Y-%m-%d")
                deposits.setdefault(isodate, _blank_deposit(isodate)).value = clean_money(amount)  # type: ignore[assignment]

            assets = [
                Asset(name="Cuenta corriente", flows=[Cashflow(date.today(), balance)]),
                *deposits.values(),
            ]

            return assets, [flow for asset in assets for flow in asset.cashflows]
        finally:
            logging.info("Logging out from Banco de Chile.")
            await browser.close()
