"""Growth factors from the committed aggregate snapshots.

A factor converts a wave-``t`` real dollar amount per household into its
projected wave-``t+3`` amount in the same real dollars. With nominal aggregate
levels ``A``, household counts ``H`` and the Fed's September CPI-U-RS ``P``::

    factor = (A[t+3] / A[t]) / (H[t+3] / H[t]) / (P[t+3] / P[t])

Dividing by household growth keeps the projection per household, since the
weights (and so the number of households) stay at their wave-``t`` values.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pandas as pd

from wealthdata.sources import AGGREGATES_DIR

#: Quarter of the survey year whose end-of-period level stands for the wave.
DEFAULT_QUARTER = 3

#: Households; net worth (FRED BOGZ1FL192090005Q), the series the 2019 README
#: names for the projection.
HOUSEHOLD_NET_WORTH = "BOGZ1FL192090005Q"
#: Households and nonprofit organizations; net worth (Z.1 table S1M.b).
HOUSEHOLD_NONPROFIT_NET_WORTH = "FL152090005"

#: Financial Accounts series whose growth scales each balance sheet class.
#: A class with two series uses their sum.
CLASS_SERIES: dict[str, tuple[str, ...]] = {
    "equities": ("LM153064475",),
    "deposits": ("FL154000005", "FL153034005"),
    "other_financial": ("LM154022375",),
    "housing": ("LM155035015",),
    "business": ("LM153081115",),
    "other_nonfinancial": ("LM155111005",),
    "debt": ("FL154190005",),
}

#: DFA vintages by the label the backtest uses for them.
DFA_FILES = {
    "current": "dfa_networth_levels_current.csv",
    "wayback_20230922": "dfa_networth_levels_wayback_20230922.csv",
    "alfred_20200630": "dfa_networth_alfred_20200630.csv",
}

#: The DFA vintage that stood before each target wave's SCF was published.
#: Earlier target waves have no such vintage: the DFA first appeared in 2019.
DFA_REAL_TIME_VINTAGE = {2019: "alfred_20200630", 2022: "wayback_20230922", 2025: "current"}

#: ALFRED vintage of the README series as of 30 June after each target wave.
NET_WORTH_REAL_TIME_VINTAGE = {2019: "2020-06-30", 2022: "2023-06-30", 2025: "2026-06-30"}


def _path(name: str) -> Path:
    return AGGREGATES_DIR / name


def _quarter_label(date: pd.Series) -> pd.Series:
    stamp = pd.to_datetime(date)
    return stamp.dt.year.astype(str) + "-Q" + stamp.dt.quarter.astype(str)


@cache
def cpi_u_rs() -> dict[int, int]:
    table = pd.read_csv(_path("cpi_u_rs_september.csv"))
    return dict(zip(table["year"], table["cpi_u_rs_september_x10"], strict=True))


@cache
def households() -> dict[int, float]:
    """Households in thousands by year (Census CPS ASEC, FRED TTLHH)."""
    table = pd.read_csv(_path("fred_TTLHH.csv"))
    years = pd.to_datetime(table["date"]).dt.year
    return dict(zip(years, table["value"].astype(float), strict=True))


@cache
def z1() -> pd.DataFrame:
    """Z.1 levels in millions of dollars, indexed by quarter (``2022-Q3``)."""
    table = pd.read_csv(_path("z1_household_balance_sheet.csv"))
    return table.pivot(index="date", columns="series", values="value").astype(float)


@cache
def household_net_worth(vintage: str | None = None) -> pd.Series:
    """Households; net worth by quarter, optionally as of an ALFRED vintage."""
    if vintage is None:
        table = pd.read_csv(_path(f"fred_{HOUSEHOLD_NET_WORTH}.csv"))
    else:
        table = pd.read_csv(_path(f"alfred_{HOUSEHOLD_NET_WORTH}.csv"))
        table = table[table["vintage"] == vintage]
        if table.empty:
            raise KeyError(f"no {HOUSEHOLD_NET_WORTH} vintage {vintage}")
    return pd.Series(table["value"].astype(float).to_numpy(), index=_quarter_label(table["date"]))


@cache
def dfa(vintage: str = "current") -> pd.DataFrame:
    """DFA net worth (millions of dollars) by quarter and wealth group."""
    table = pd.read_csv(_path(DFA_FILES[vintage]))
    if "Date" in table.columns:
        tidy = pd.DataFrame(
            {
                "date": table["Date"].str.replace(":", "-"),
                "category": table["Category"],
                "net_worth": table["Net worth"].astype(float),
            }
        )
    else:
        tidy = pd.DataFrame(
            {
                "date": _quarter_label(table["date"]),
                "category": table["category"],
                "net_worth": table["net_worth"].astype(float),
            }
        )
    return tidy.pivot(index="date", columns="category", values="net_worth")


def label(year: int, quarter: int = DEFAULT_QUARTER) -> str:
    return f"{year}-Q{quarter}"


def price_ratio(base: int, target: int) -> float:
    cpi = cpi_u_rs()
    return cpi[target] / cpi[base]


def household_ratio(base: int, target: int) -> float:
    count = households()
    return count[target] / count[base]


def real_per_household(
    nominal_ratio: float, base: int, target: int, *, per_household: bool = True
) -> float:
    """Convert nominal aggregate growth into a real per-household factor."""
    factor = nominal_ratio / price_ratio(base, target)
    if per_household:
        factor /= household_ratio(base, target)
    return float(factor)


def _ratio(levels: pd.Series, base: int, target: int, quarter: int) -> float:
    return float(levels[label(target, quarter)] / levels[label(base, quarter)])


def net_worth_factor(
    base: int,
    target: int,
    *,
    quarter: int = DEFAULT_QUARTER,
    per_household: bool = True,
    series: str = HOUSEHOLD_NET_WORTH,
    vintage: str | None = None,
) -> float:
    """Uniform scaling factor from aggregate household net worth growth."""
    if series == HOUSEHOLD_NET_WORTH:
        levels = household_net_worth(vintage)
    elif vintage is None:
        levels = z1()[series]
    else:
        raise ValueError("vintages are available only for the households series")
    return real_per_household(
        _ratio(levels, base, target, quarter), base, target, per_household=per_household
    )


def class_factors(
    base: int, target: int, *, quarter: int = DEFAULT_QUARTER, per_household: bool = True
) -> dict[str, float]:
    """One factor per balance sheet class from its Financial Accounts series."""
    table = z1()
    return {
        name: real_per_household(
            _ratio(table[list(series)].sum(axis=1), base, target, quarter),
            base,
            target,
            per_household=per_household,
        )
        for name, series in CLASS_SERIES.items()
    }


def dfa_group_factors(
    base: int,
    target: int,
    *,
    vintage: str = "current",
    groups: tuple[str, ...] | None = None,
    quarter: int = DEFAULT_QUARTER,
) -> dict[str, float]:
    """One factor per DFA wealth group from that group's net worth growth.

    A wealth group is a fixed share of households, so its household count
    grows at the national rate. ``groups`` may name ``Top1`` to merge the two
    top groups of a five-group vintage.
    """
    table = dfa(vintage).copy()
    if "Top1" not in table.columns:
        table["Top1"] = table["TopPt1"] + table["RemainingTop1"]
    if groups is None:
        groups = tuple(name for name in dfa(vintage).columns)
    return {
        name: real_per_household(_ratio(table[name], base, target, quarter), base, target)
        for name in groups
    }
