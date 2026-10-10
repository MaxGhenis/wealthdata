"""Project each wave three years forward and score it against the next wave.

``python -m wealthdata.backtest --through 2022`` runs every wave pair whose
target is at most 2022. The 2025 target needs the 2025 extract to be pinned
(see :mod:`wealthdata.scf`).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from wealthdata import aggregates, project, replicates, scf, stats

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"

#: Statistics whose errors are percentages of the actual value.
LEVEL_STATS: tuple[str, ...] = ("mean", "p25", "p50", "p75", "p90", "p99")
#: Statistics on a 0-1 scale whose errors are percentage points.
DISTRIBUTION_STATS: tuple[str, ...] = ("top10_share", "top1_share", "gini")
SUBGROUP_STATS: tuple[str, ...] = (
    *(f"median_age_{code}" for code in scf.AGE_LABELS),
    *(f"median_race_{code}" for code in scf.RACE_LABELS),
)

Sheets = dict[int, pd.DataFrame]


@dataclass(frozen=True)
class Method:
    """A projection rule.

    ``role`` is ``primary`` for the four pre-specified contenders,
    ``sensitivity`` for pre-listed variants, and ``oracle`` for diagnostics
    that use the target wave and so are not forecasts.
    """

    name: str
    role: str
    description: str
    project: Callable[[Sheets, int, int], tuple[pd.DataFrame, dict[str, float]] | None]
    #: Whether the projection depends on the weights (wealth groups do).
    weight_dependent: bool = False


def _no_change(sheets: Sheets, base: int, target: int):
    return project.no_change(sheets[base]), {}


def _uniform(**options):
    def run(sheets: Sheets, base: int, target: int):
        vintage = options.get("vintage")
        if vintage == "real_time":
            vintage = aggregates.NET_WORTH_REAL_TIME_VINTAGE.get(target)
            if vintage is None:
                return None
        factor = aggregates.net_worth_factor(base, target, **{**options, "vintage": vintage})
        return project.scale_uniform(sheets[base], factor), {"all": factor}

    return run


def _classes(**options):
    def run(sheets: Sheets, base: int, target: int):
        factors = aggregates.class_factors(base, target, **options)
        return project.scale_classes(sheets[base], factors), factors

    return run


def _dfa(vintage: str = "current", groups: dict[str, float] | None = None):
    def run(sheets: Sheets, base: int, target: int):
        chosen = vintage
        if vintage == "real_time":
            chosen = aggregates.DFA_REAL_TIME_VINTAGE.get(target)
            if chosen is None:
                return None
        bounds = groups
        if bounds is None:
            five = "TopPt1" in aggregates.dfa(chosen).columns
            bounds = project.DFA_GROUPS_5 if five else project.DFA_GROUPS_4
        factors = aggregates.dfa_group_factors(base, target, vintage=chosen, groups=tuple(bounds))
        return project.scale_wealth_groups(sheets[base], factors, bounds), factors

    return run


def _per_household_mean(sheet: pd.DataFrame, column: str) -> float:
    return float(np.sum(sheet[column] * sheet["wgt"]) / np.sum(sheet["wgt"]))


def _oracle_uniform(sheets: Sheets, base: int, target: int):
    factor = _per_household_mean(sheets[target], "networth") / _per_household_mean(
        sheets[base], "networth"
    )
    return project.scale_uniform(sheets[base], factor), {"all": factor}


def _oracle_classes(sheets: Sheets, base: int, target: int):
    factors = {
        name: _per_household_mean(sheets[target], name) / _per_household_mean(sheets[base], name)
        for name in project.CLASSES
    }
    return project.scale_classes(sheets[base], factors), factors


METHODS: tuple[Method, ...] = (
    Method("a_no_change", "primary", "no change in real dollars", _no_change),
    Method(
        "b_uniform",
        "primary",
        "uniform scaling by real household net worth growth per household",
        _uniform(),
    ),
    Method(
        "c_asset_class",
        "primary",
        "each balance sheet class scaled by its Financial Accounts series",
        _classes(),
    ),
    Method(
        "d_dfa_groups",
        "primary",
        "each DFA wealth group scaled by its net worth growth (current vintage)",
        _dfa(),
        weight_dependent=True,
    ),
    Method(
        "b_uniform_aggregate",
        "sensitivity",
        "uniform scaling by real aggregate growth, no household adjustment",
        _uniform(per_household=False),
    ),
    Method("b_uniform_q2", "sensitivity", "uniform scaling, Q2 levels", _uniform(quarter=2)),
    Method("b_uniform_q4", "sensitivity", "uniform scaling, Q4 levels", _uniform(quarter=4)),
    Method(
        "b_uniform_nonprofits",
        "sensitivity",
        "uniform scaling by households and nonprofits net worth",
        _uniform(series=aggregates.HOUSEHOLD_NONPROFIT_NET_WORTH),
    ),
    Method(
        "b_uniform_real_time",
        "sensitivity",
        "uniform scaling with the series as published before the target SCF",
        _uniform(vintage="real_time"),
    ),
    Method("c_asset_class_q2", "sensitivity", "class scaling, Q2 levels", _classes(quarter=2)),
    Method("c_asset_class_q4", "sensitivity", "class scaling, Q4 levels", _classes(quarter=4)),
    Method(
        "d_dfa_groups_top1",
        "sensitivity",
        "DFA scaling with the top 1% as one group (current vintage)",
        _dfa(groups=project.DFA_GROUPS_4),
        weight_dependent=True,
    ),
    Method(
        "d_dfa_groups_real_time",
        "sensitivity",
        "DFA scaling with the vintage published before the target SCF",
        _dfa(vintage="real_time"),
        weight_dependent=True,
    ),
    Method(
        "o_uniform_oracle",
        "oracle",
        "uniform scaling by the SCF's own mean growth (uses the target wave)",
        _oracle_uniform,
    ),
    Method(
        "o_asset_class_oracle",
        "oracle",
        "class scaling by the SCF's own class growth (uses the target wave)",
        _oracle_classes,
    ),
)


def pairs(through: int) -> list[tuple[int, int]]:
    return [(base, base + 3) for base in scf.WAVES[:-1] if base + 3 <= through]


def score_rows(projected: dict[str, float], actual: dict[str, float]) -> list[dict]:
    """Compare projected statistics with the actual wave's, one row each.

    ``error`` is projected minus actual. ``pct_error`` is the error as a
    percentage of the actual value, defined for dollar statistics with a
    positive actual. ``scaled_error`` is the single number each statistic
    contributes to the summary scores: the percentage error for dollar
    statistics (for ``p10``, the error as a percentage of the actual median,
    because the tenth percentile sits near zero) and percentage points for
    shares and the Gini coefficient.
    """
    rows = []
    for name, value in projected.items():
        truth = actual[name]
        error = value - truth
        if name in DISTRIBUTION_STATS:
            pct, scaled = np.nan, 100.0 * error
        elif name == "p10":
            pct = 100.0 * error / truth if truth > 0 else np.nan
            scaled = 100.0 * error / actual["p50"]
        else:
            pct = 100.0 * error / truth if truth > 0 else np.nan
            scaled = pct
        rows.append(
            {
                "stat": name,
                "projected": value,
                "actual": truth,
                "error": error,
                "pct_error": pct,
                "scaled_error": scaled,
            }
        )
    return rows


def run(
    through: int, *, estimator: Callable[[pd.DataFrame], dict[str, float]] = stats.across_implicates
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the backtest. Returns scores, factors and actual-wave statistics."""
    years = [year for year in scf.WAVES if year <= through]
    sheets = {year: project.balance_sheet(scf.load_wave(year)) for year in years}
    actual = {year: estimator(sheets[year]) for year in years}

    wave_rows = []
    for year in years:
        sheet = sheets[year]
        households = float(sheet["wgt"].sum())
        wave_rows += [
            {"wave": year, "stat": name, "value": value} for name, value in actual[year].items()
        ]
        wave_rows.append({"wave": year, "stat": "households", "value": households})
        wave_rows.append({"wave": year, "stat": "sample_households", "value": len(sheet) / 5})
        for name in project.CLASSES:
            wave_rows.append(
                {"wave": year, "stat": f"mean_{name}", "value": _per_household_mean(sheet, name)}
            )

    score, factor = [], []
    for base, target in pairs(through):
        for method in METHODS:
            outcome = method.project(sheets, base, target)
            if outcome is None:
                continue
            projected, factors = outcome
            if not projected["wgt"].equals(sheets[base]["wgt"]):
                raise AssertionError(f"{method.name} changed the weights")
            key = {"base": base, "target": target, "method": method.name, "role": method.role}
            score += [{**key, **row} for row in score_rows(estimator(projected), actual[target])]
            factor += [{**key, "item": item, "factor": value} for item, value in factors.items()]
    return pd.DataFrame(score), pd.DataFrame(factor), pd.DataFrame(wave_rows)


def summarize(scores: pd.DataFrame) -> pd.DataFrame:
    """Three summary scores per wave pair and method.

    Each is a mean absolute error: ``level`` over the mean and five quantiles
    (percent), ``distribution`` over the two top shares and the Gini
    coefficient (percentage points), ``subgroup`` over the ten group medians
    (percent).
    """
    families = {
        "level": LEVEL_STATS,
        "distribution": DISTRIBUTION_STATS,
        "subgroup": SUBGROUP_STATS,
    }
    frames = []
    for family, names in families.items():
        subset = scores[scores["stat"].isin(names)]
        grouped = subset.groupby(["base", "target", "method", "role"], sort=False)
        if grouped["scaled_error"].apply(lambda errors: errors.isna().any()).any():
            raise ValueError(f"undefined error in the {family} score")
        frame = grouped["scaled_error"].apply(lambda errors: errors.abs().mean()).reset_index()
        frame.insert(4, "score", family)
        frames.append(frame.rename(columns={"scaled_error": "mean_abs_error"}))
    return pd.concat(frames, ignore_index=True)


#: Methods whose projected statistics get standard errors.
NOISE_METHODS: tuple[str, ...] = (
    "a_no_change",
    "b_uniform",
    "c_asset_class",
    "d_dfa_groups",
    "d_dfa_groups_real_time",
)

#: An error within this many standard errors of zero is called within noise.
NOISE_THRESHOLD = 1.96


def standard_errors(through: int) -> pd.DataFrame:
    """Standard errors of the actual and projected statistics.

    One row per statistic for each wave (``method`` is ``actual``, ``base``
    equal to ``target``) and for each wave pair and method in
    :data:`NOISE_METHODS`.
    """
    years = [year for year in scf.WAVES if year <= through]
    sheets = {year: project.balance_sheet(scf.load_wave(year)) for year in years}
    weights = {year: replicates.load(year) for year in years}
    frames = []
    for year in years:
        frame = replicates.standard_errors(sheets[year], weights[year]).reset_index()
        frame.insert(0, "method", "actual")
        frame.insert(0, "target", year)
        frame.insert(0, "base", year)
        frames.append(frame)
    methods = {method.name: method for method in METHODS}
    for base, target in pairs(through):
        for name in NOISE_METHODS:
            method = methods[name]
            if method.project(sheets, base, target) is None:
                continue

            def projector(frame, method=method, base=base, target=target):
                return method.project({base: frame}, base, target)[0]

            frame = replicates.standard_errors(
                sheets[base],
                weights[base],
                projector=projector,
                reproject=method.weight_dependent,
            ).reset_index()
            frame.insert(0, "method", name)
            frame.insert(0, "target", target)
            frame.insert(0, "base", base)
            frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def add_noise(scores: pd.DataFrame, errors: pd.DataFrame) -> pd.DataFrame:
    """Attach the standard error of each error and its ratio to that error.

    The projected and actual statistics come from independent samples, so
    the variance of their difference is the sum of their variances.
    """
    actual = errors[errors["method"] == "actual"][["target", "stat", "se"]]
    projected = errors[errors["method"] != "actual"][["base", "target", "method", "stat", "se"]]
    merged = scores.merge(
        projected.rename(columns={"se": "se_projected"}),
        on=["base", "target", "method", "stat"],
        how="left",
        validate="one_to_one",
    ).merge(
        actual.rename(columns={"se": "se_actual"}),
        on=["target", "stat"],
        how="left",
        validate="many_to_one",
    )
    merged["se_error"] = np.sqrt(merged["se_projected"] ** 2 + merged["se_actual"] ** 2)
    merged["z"] = merged["error"] / merged["se_error"]
    return merged


def write(through: int, out_dir: Path = RESULTS_DIR, *, noise: bool = True) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    scores, factors, waves = run(through)
    if noise:
        errors = standard_errors(through)
        errors.to_csv(out_dir / "standard_errors.csv", index=False, float_format="%.10g")
        scores = add_noise(scores, errors)
    scores.to_csv(out_dir / "scores.csv", index=False, float_format="%.10g")
    factors.to_csv(out_dir / "factors.csv", index=False, float_format="%.10g")
    waves.to_csv(out_dir / "wave_stats.csv", index=False, float_format="%.10g")
    summarize(scores).to_csv(out_dir / "summary.csv", index=False, float_format="%.10g")
    pooled_scores, _, _ = run(through, estimator=stats.pooled)
    pooled_scores.to_csv(out_dir / "scores_pooled.csv", index=False, float_format="%.10g")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", type=int, default=scf.WAVES[-1], help="latest target wave")
    parser.add_argument("--no-noise", action="store_true", help="skip standard errors")
    arguments = parser.parse_args()
    write(arguments.through, noise=not arguments.no_noise)
    table = pd.read_csv(RESULTS_DIR / "summary.csv")
    primary = table[table["role"] == "primary"]
    print(primary.pivot_table(index="method", columns="score", values="mean_abs_error").round(2))
