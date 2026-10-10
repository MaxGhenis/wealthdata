"""Age a wave's balance sheets forward.

Every method multiplies dollar amounts by factors and leaves households,
demographics and weights exactly as they were. Net worth is always recomputed
from the scaled classes, so the balance sheet identity holds after every
projection.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

ASSET_CLASSES: tuple[str, ...] = (
    "equities",
    "deposits",
    "other_financial",
    "housing",
    "business",
    "other_nonfinancial",
)
CLASSES: tuple[str, ...] = (*ASSET_CLASSES, "debt")

#: Columns a projection never touches.
FIXED_COLUMNS: tuple[str, ...] = ("case", "implicate", "wgt", "agecl", "racecl4")

#: Wealth groups of the Distributional Financial Accounts as upper percentile
#: bounds, lowest group first. The five-group split divides the top 1% at the
#: 99.9th percentile.
DFA_GROUPS_5: dict[str, float] = {
    "Bottom50": 0.50,
    "Next40": 0.90,
    "Next9": 0.99,
    "RemainingTop1": 0.999,
    "TopPt1": 1.0,
}
DFA_GROUPS_4: dict[str, float] = {"Bottom50": 0.50, "Next40": 0.90, "Next9": 0.99, "Top1": 1.0}


def balance_sheet(wave: pd.DataFrame) -> pd.DataFrame:
    """Partition each household's net worth into seven classes.

    The six asset classes and debt are exhaustive: assets sum to the
    extract's ``fin + nfin``. ``equity`` has, since 2007, counted savings
    accounts invested in stocks, which ``liq`` also counts, so
    ``other_financial`` is negative for the few households where that overlap
    exceeds their remaining financial assets.
    """
    sheet = wave[list(FIXED_COLUMNS)].copy()
    sheet["equities"] = wave["equity"]
    sheet["deposits"] = wave["liq"] + wave["cds"]
    sheet["other_financial"] = wave["fin"] - wave["equity"] - wave["liq"] - wave["cds"]
    sheet["housing"] = wave["houses"] + wave["oresre"]
    sheet["business"] = wave["bus"] + wave["nnresre"]
    sheet["other_nonfinancial"] = (
        wave["nfin"] - wave["houses"] - wave["oresre"] - wave["bus"] - wave["nnresre"]
    )
    sheet["debt"] = wave["debt"]
    sheet["networth"] = net_worth(sheet)
    return sheet


def net_worth(sheet: pd.DataFrame) -> pd.Series:
    return sheet[list(ASSET_CLASSES)].sum(axis=1) - sheet["debt"]


def _scaled(sheet: pd.DataFrame, factors: pd.DataFrame | np.ndarray) -> pd.DataFrame:
    """Multiply the class columns by ``factors`` (rows by classes) and re-add."""
    values = np.asarray(factors, dtype="float64")
    if not (np.isfinite(values).all() and (values > 0).all()):
        raise ValueError("scaling factors must be positive and finite")
    projected = sheet.copy()
    projected[list(CLASSES)] = sheet[list(CLASSES)].to_numpy() * values
    projected["networth"] = net_worth(projected)
    return projected


def no_change(sheet: pd.DataFrame) -> pd.DataFrame:
    """Hold every real dollar amount fixed."""
    return _scaled(sheet, np.ones((1, len(CLASSES))))


def scale_uniform(sheet: pd.DataFrame, factor: float) -> pd.DataFrame:
    """Multiply every class of every household by the same factor."""
    return _scaled(sheet, np.full((1, len(CLASSES)), float(factor)))


def scale_classes(sheet: pd.DataFrame, factors: Mapping[str, float]) -> pd.DataFrame:
    """Multiply each class by its own factor, the same for every household."""
    if set(factors) != set(CLASSES):
        raise ValueError(f"expected one factor for each of {CLASSES}")
    return _scaled(sheet, np.array([[float(factors[name]) for name in CLASSES]]))


def wealth_group(networth, weights, bounds: Mapping[str, float]) -> np.ndarray:
    """Assign each household to a wealth group by weighted net worth rank.

    Households are ranked by net worth (ties keep their input order) and
    placed by the midpoint of the weight interval they occupy, so a household
    belongs to exactly one group.
    """
    x = np.asarray(networth, dtype="float64")
    w = np.asarray(weights, dtype="float64")
    order = np.argsort(x, kind="stable")
    cumulative = np.cumsum(w[order])
    midpoint = (cumulative - w[order] / 2.0) / cumulative[-1]
    names = list(bounds)
    uppers = np.array([bounds[name] for name in names])
    if not (np.all(np.diff(uppers) > 0) and uppers[-1] == 1.0):
        raise ValueError("bounds must increase and end at 1")
    index = np.minimum(np.searchsorted(uppers, midpoint, side="left"), len(names) - 1)
    groups = np.empty(x.size, dtype=object)
    groups[order] = np.array(names, dtype=object)[index]
    return groups


def scale_wealth_groups(
    sheet: pd.DataFrame, factors: Mapping[str, float], bounds: Mapping[str, float]
) -> pd.DataFrame:
    """Multiply every class of a household by its wealth group's factor.

    Groups are assigned within each implicate from that implicate's own net
    worth ranking.
    """
    if set(factors) != set(bounds):
        raise ValueError("factors and bounds must name the same groups")
    row_factor = pd.Series(np.nan, index=sheet.index)
    for _, implicate in sheet.groupby("implicate", sort=True):
        groups = wealth_group(implicate["networth"].to_numpy(), implicate["wgt"].to_numpy(), bounds)
        row_factor.loc[implicate.index] = [float(factors[name]) for name in groups]
    return _scaled(sheet, row_factor.to_numpy()[:, None] * np.ones((1, len(CLASSES))))
