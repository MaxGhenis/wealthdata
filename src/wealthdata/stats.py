"""Weighted distribution statistics for net worth.

All functions take values and positive weights. Net worth can be negative, so
nothing here assumes nonnegative values; shares and the Gini coefficient
require only a positive weighted total.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

QUANTILES: dict[str, float] = {
    "p10": 0.10,
    "p25": 0.25,
    "p50": 0.50,
    "p75": 0.75,
    "p90": 0.90,
    "p99": 0.99,
}


def _arrays(values, weights) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(values, dtype="float64")
    w = np.asarray(weights, dtype="float64")
    if x.ndim != 1 or x.shape != w.shape:
        raise ValueError("values and weights must be one-dimensional and the same length")
    if x.size == 0:
        raise ValueError("no observations")
    if not (np.isfinite(x).all() and np.isfinite(w).all()):
        raise ValueError("values and weights must be finite")
    if not (w > 0).all():
        raise ValueError("weights must be positive")
    return x, w


def weighted_mean(values, weights) -> float:
    x, w = _arrays(values, weights)
    return float(np.sum(x * w) / np.sum(w))


def weighted_quantile(values, weights, q: float) -> float:
    """Inverse of the weighted empirical CDF.

    Returns the smallest observed value whose cumulative weight share is at
    least ``q``: an observed value, never an interpolation.
    """
    if not 0 < q <= 1:
        raise ValueError("q must be in (0, 1]")
    x, w = _arrays(values, weights)
    order = np.argsort(x, kind="stable")
    x, w = x[order], w[order]
    cumulative = np.cumsum(w)
    target = q * cumulative[-1]
    # Guard against the last cumulative sum falling a rounding error short.
    index = min(int(np.searchsorted(cumulative, target, side="left")), x.size - 1)
    return float(x[index])


def _lorenz(values, weights) -> tuple[np.ndarray, np.ndarray]:
    """Lorenz curve vertices: population share and wealth share, from (0, 0)."""
    x, w = _arrays(values, weights)
    order = np.argsort(x, kind="stable")
    x, w = x[order], w[order]
    total = np.sum(x * w)
    if not total > 0:
        raise ValueError("shares need a positive weighted total")
    population = np.concatenate([[0.0], np.cumsum(w) / np.sum(w)])
    wealth = np.concatenate([[0.0], np.cumsum(x * w) / total])
    population[-1] = 1.0
    wealth[-1] = 1.0
    return population, wealth


def top_share(values, weights, fraction: float) -> float:
    """Share of the total held by the top ``fraction`` of the weighted population.

    A household straddling the cutoff is split in proportion to its weight
    (linear interpolation along the Lorenz curve).
    """
    if not 0 < fraction < 1:
        raise ValueError("fraction must be in (0, 1)")
    population, wealth = _lorenz(values, weights)
    return float(1.0 - np.interp(1.0 - fraction, population, wealth))


def gini(values, weights) -> float:
    """Gini coefficient of the weighted distribution.

    One minus twice the area under the Lorenz curve, which equals the mean
    absolute difference between two draws divided by twice the mean.
    """
    population, wealth = _lorenz(values, weights)
    area = np.sum(np.diff(population) * (wealth[1:] + wealth[:-1]) / 2.0)
    return float(1.0 - 2.0 * area)


def summary(frame: pd.DataFrame, value: str = "networth", weight: str = "wgt") -> dict[str, float]:
    """Every scored statistic for one implicate (or any single weighted sample)."""
    x = frame[value].to_numpy()
    w = frame[weight].to_numpy()
    result = {"mean": weighted_mean(x, w)}
    for name, q in QUANTILES.items():
        result[name] = weighted_quantile(x, w, q)
    result["top10_share"] = top_share(x, w, 0.10)
    result["top1_share"] = top_share(x, w, 0.01)
    result["gini"] = gini(x, w)
    for column, prefix in (("agecl", "median_age"), ("racecl4", "median_race")):
        for code, group in frame.groupby(column, sort=True):
            result[f"{prefix}_{code}"] = weighted_quantile(
                group[value].to_numpy(), group[weight].to_numpy(), 0.5
            )
    return result


def across_implicates(
    frame: pd.DataFrame, statistic: Callable[[pd.DataFrame], dict[str, float]] = summary
) -> dict[str, float]:
    """Compute ``statistic`` on each implicate and average the results.

    This is the multiple-imputation point estimate: the mean over implicates
    of the complete-data estimate.
    """
    per_implicate = [statistic(group) for _, group in frame.groupby("implicate", sort=True)]
    return {key: float(np.mean([item[key] for item in per_implicate])) for key in per_implicate[0]}


def pooled(
    frame: pd.DataFrame, statistic: Callable[[pd.DataFrame], dict[str, float]] = summary
) -> dict[str, float]:
    """Compute ``statistic`` once on the five implicates stacked together."""
    return statistic(frame)
