"""
asset.py
--------
This module contains two core financial concepts: assets and cashflows.
"""

from __future__ import annotations

import sys
from datetime import date
from typing import TypeAlias

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from pyxirr import xirr
from rich.table import Table

from patry import SETTINGS

DAYS_IN_YEAR = 365.25


class Cashflow:
    def __init__(self, purchase_date: date, amount: float) -> None:
        """
        >>> flow = Cashflow(date.fromisoformat("2023-01-30"), 1.0)
        >>> flow
        Cashflow(purchase_date=2023-01-30, amount=1)
        >>> print(flow)
        (2023-01-30, $1)
        """

        self.purchase_date = purchase_date
        self.amount = amount  # type: ignore[assignment]

    @property
    def amount(self) -> int:
        return self._amount

    @amount.setter
    def amount(self, value: float) -> None:
        self._amount = int(value)

    @property
    def elapsed_days(self) -> int:
        return (SETTINGS.today - self.purchase_date).days

    def astuple(self) -> tuple[date, int]:
        return self.purchase_date, self.amount

    def asline(self) -> str:
        """
        >>> Cashflow(purchase_date=date(2023, 1, 30), amount=1234).asline()
        '2023-01-30,1_234'

        Note: Cashflow.fromline(<line>) is the inverse.
        """

        return f"{self.purchase_date},{self.amount:_}"

    @classmethod
    def fromline(cls, line: str) -> Self:
        """
        >>> Cashflow.fromline(line := "2023-01-30,1_234").asline() == line
        True
        """

        isodate, amount = line.split(",")
        return cls(date.fromisoformat(isodate), int(amount))

    def __str__(self) -> str:
        return f"({self.purchase_date}, {Asset.as_currency(self.amount)})"

    def __repr__(self) -> str:
        return f"Cashflow(purchase_date={self.purchase_date}, amount={self.amount})"


class Asset:
    def __init__(self, flows: list[Cashflow], value: float | None = None, name: str = "") -> None:
        """
        * Example 0: Creating an blank asset, i.e. without cashflows.

        >>> zero_flows = Asset([], 100)
        >>> print(zero_flows)
        () $0->$100
        >>> zero_flows.outlay, zero_flows.profit, zero_flows.profit_ratio, zero_flows.growth_rate
        (0, None, None, None)

        * Example 1a: Creating an asset with a single cashflow.

        >>> from datetime import timedelta
        >>> cashflow_14d = Cashflow(date.today() - timedelta(days=14), 250)
        >>> time_deposit = Asset([cashflow_14d], 264, "First time deposit")
        >>> print(time_deposit)
        (First time deposit) $250->$264

        >>> time_deposit.elapsed_days
        14
        >>> time_deposit.outlay
        250
        >>> time_deposit.profit
        14
        >>> f"{time_deposit.profit_ratio:.1%}"
        '5.6%'
        >>> round(time_deposit.growth_rate, 2)
        3.14
        >>> round(time_deposit.weighted_time, 2)
        0.04

        * Example 1b: Appending an earlier cashflow to the previous asset.

        >>> cashflow_60d = Cashflow(date.today() - timedelta(days=60), 10)
        >>> time_deposit.cashflows.append(cashflow_60d)
        >>> print(time_deposit)
        (First time deposit) $260->$264

        >>> time_deposit.elapsed_days
        60
        >>> time_deposit.outlay
        260
        >>> time_deposit.profit
        4
        >>> f"{time_deposit.profit_ratio:.1%}"
        '1.5%'
        >>> round(time_deposit.growth_rate, 2)
        0.42
        >>> round(time_deposit.weighted_time, 2)
        0.04
        """

        self.cashflows = flows
        self.value = value  # type: ignore[assignment]
        self.name = name

    @property
    def value(self) -> int:
        """
        Return the asset's current value, defaulting to the outlay if unspecified.
        """

        return self._value or self.outlay

    @value.setter
    def value(self, value: float | None) -> None:
        self._value = None if value is None else int(value)

    @property
    def elapsed_days(self) -> int:
        """
        Calculate the number of days since the asset was purchased.
        """

        return (SETTINGS.today - min(flow.purchase_date for flow in self.cashflows)).days

    @property
    def weighted_time(self) -> float | None:
        """
        Calculate the weighted time of investment in years.
        """

        if self.outlay == 0:
            return None

        all_cashflows = ((flow.amount, flow.elapsed_days) for flow in self.cashflows)
        weighted_days = sum(weight * days for weight, days in all_cashflows) / self.outlay
        return weighted_days / DAYS_IN_YEAR

    @property
    def outlay(self) -> int:
        """
        Calculate the outlay by adding all cashflows.
        """

        return sum(cashflow.amount for cashflow in self.cashflows)

    @property
    def profit(self) -> int | None:
        """
        Calculate the profit made from the asset.
        """

        return self.value - self.outlay if self.outlay != 0 else None

    @property
    def profit_ratio(self) -> float | None:
        """
        Calculate the "return on investment", also known as the ROI.
        <https://www.investopedia.com/terms/r/returnoninvestment.asp>

        Despite the logical guarantee that `self.profit` cannot be None when `self.outlay` isn't 0,
        static type checkers will raise an error due to their inability to infer this relationship.
        Hence, `type: ignore[operator]`.
        """

        return self.profit / self.outlay if self.outlay != 0 else None  # type: ignore[operator]

    @property
    def growth_rate(self) -> float | None:
        """
        Calculate the asset's average annual growth rate.

        a) For a singular asset, the compound annual growth rate (aka. CAGR) will be used.
        <https://www.investopedia.com/terms/c/cagr.asp>

        b) For composite assets, the extended internal rate of return (XIRR) will be used.
        <https://www.investopedia.com/terms/i/irr.asp>
        """

        # z) no-flow -> early return
        if len(self.cashflows) == 0:
            return None

        # a) CAGR
        if len(self.cashflows) == 1:
            if self.elapsed_days != 0:
                return (self.value / self.outlay) ** (DAYS_IN_YEAR / self.elapsed_days) - 1
            return None

        # b) XIRR
        # <https://anexen.github.io/pyxirr/functions.html#xirr>
        cashtuples = (cf.astuple() for cf in self.cashflows)
        return xirr([*cashtuples, (SETTINGS.today, -self.value)])

    def __str__(self) -> str:
        return f"({self.name}) {self.as_currency(self.outlay)}->{self.as_currency(self.value)}"

    @staticmethod
    def as_currency(number: int | str) -> str:
        """
        Convert a number to a formatted currency string.

        >>> Asset.as_currency(1234)
        '$1.234'
        >>> Asset.as_currency(1_234)
        '$1.234'
        >>> Asset.as_currency("1234")
        '$1.234'
        >>> Asset.as_currency("1_234")
        '$1.234'

        Note: utils.clean_money(<number>) is the inverse.
        """

        return f"${int(number):,}".replace(",", ".")


class AssetTable(Table):
    class Subtotal(Asset):
        style = "white"

    class Section:
        """
        This is a sentinel class to represent table sections.
        """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._initialize_columns()

        self.rows_: list[Asset | AssetTable.Section] = []
        self.cashflows: list[Cashflow] = []

    def _initialize_columns(self) -> None:
        columns: list[tuple] = [
            ("Name", "yellow", "left"),
            ("Outlay CLP", "cyan", "right"),
            ("Value CLP", "blue", "right"),
            ("Total %", "blue", "right"),
            ("Delta CLP", "green", "right"),
            ("Delta %", "green", "right"),
            ("CAGR %", "yellow", "right"),
            ("Time", "yellow", "right"),
        ]

        if SETTINGS.usdtoclp:
            columns.insert(SETTINGS.usdindex, ("Value USD", "blue", "right"))

        for name, style, justify in columns:
            self.add_column(name, style=style, justify=justify)

    @staticmethod
    def build_row(asset: Asset, total: int) -> list[str]:
        """
        >>> from datetime import date
        >>> zero = Asset([], 50, "A0")
        >>> AssetTable.build_row(zero, 50)
        ['A0', 'n/a', '$50', '100.0%', 'n/a', 'n/a', 'n/a', 'n/a']

        >>> one = Asset([Cashflow(date.today(), 100)], 100, "A1")
        >>> AssetTable.build_row(one, 100)
        ['A1', '$100', '$100', '100.0%', '$0', '0.0%', 'n/a', 'n/a']

        >>> two = Asset([Cashflow(date.today(), 150)], 200, "A2")
        >>> AssetTable.build_row(two, 250)
        ['A2', '$150', '$200', '80.0%', '$50', '33.3%', 'n/a', 'n/a']
        """

        row = [
            asset.name,
            asset.as_currency(asset.outlay) if asset.cashflows else "n/a",
            asset.as_currency(asset.value),
            f"{asset.value / total:.1%}",
            asset.as_currency(asset.profit) if asset.profit is not None else "n/a",
            f"{asset.profit_ratio:.1%}" if asset.profit_ratio is not None else "n/a",
            f"{asset.growth_rate:.1%}" if asset.growth_rate is not None else "n/a",
            f"{asset.weighted_time:.1f}" if asset.weighted_time else "n/a",
        ]

        if SETTINGS.usdtoclp:
            value_usd = round(asset.value / SETTINGS.usdtoclp, -1)
            row.insert(SETTINGS.usdindex, asset.as_currency(value_usd))

        return row

    def compute(self) -> None:
        """
        Compute the entire table by using all stored assets and cashflows.
        """

        total_value = sum(row.value for row in self.rows_ if type(row) is Asset)
        total_asset = Asset(self.cashflows, total_value, "Total")

        for row in self.rows_:
            if isinstance(row, Asset):
                style = getattr(row, "style", None)
                self.add_row(*self.build_row(row, total_value), style=style)
            else:
                self.add_section()

        self.add_row(*self.build_row(total_asset, total_value), style="bold")


Portfolio: TypeAlias = tuple[list[Asset], list[Cashflow]]
