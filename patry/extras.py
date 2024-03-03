"""
extras.py
---------
This module works with extra assets, e.g. cryptocurrencies.
"""

import logging
import os

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright as playwright

from patry import SETTINGS
from patry.asset import Asset, Cashflow, Portfolio
from patry.utils import clean_money

CHILE_ID_NUMBER = os.environ["CHILE_ID_NUMBER"]
MODELO_PASSWORD = os.environ["MODELO_PASSWORD"]
MODELO_LOGIN_URL = "https://www.afpmodelo.cl/AFP/Acceso-mi-cuenta/Acceso-a-mi-Cuenta.aspx"


def _read_patry() -> list[Cashflow]:
    try:
        with open("cashflows/modelo.patry", encoding="locale") as file:
            return [Cashflow.fromline(line) for line in file]

    except FileNotFoundError:
        logging.warning("Couldn't find file with cashflows.")
        return []


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
            logging.info("Logging in to AFP Modelo.")
            await page.goto(MODELO_LOGIN_URL)
            await page.locator("#ContentPlaceHolder1_Login_Rut").fill(CHILE_ID_NUMBER)
            await page.locator("#ContentPlaceHolder1_Login_Clave").fill(MODELO_PASSWORD)
            await page.locator("#ContentPlaceHolder1_Btn_Ingresar").click()

            # Get account balance
            total = page.locator("td.txt_total_ahorrado")
            await total.first.wait_for()
            balance = clean_money((await total.all_text_contents())[-1])

        except PlaywrightError:
            logging.exception("Oops!")
            return [], []
        else:
            return [Asset(cashflows := _read_patry(), balance, "AFP Modelo")], cashflows

        finally:
            logging.info("Logging out from AFP Modelo.")
            await browser.close()
