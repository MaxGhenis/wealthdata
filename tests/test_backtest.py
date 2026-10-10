"""Scoring rules, plus end-to-end checks against the SCF data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from wealthdata import backtest, project, replicates, scf, stats

dollars = st.floats(min_value=1.0, max_value=1e8)
shares = st.floats(min_value=0.01, max_value=0.99)

LAST_PINNED = max(int(year) for year in scf.pins())


@given(dollars, dollars, shares, shares, dollars)
def test_score_rows_follow_their_definitions(projected, actual, share, actual_share, median):
    rows = backtest.score_rows(
        {"mean": projected, "p10": projected, "p50": median, "gini": share},
        {"mean": actual, "p10": actual, "p50": median, "gini": actual_share},
    )
    by_stat = {row["stat"]: row for row in rows}
    assert by_stat["mean"]["error"] == projected - actual
    assert by_stat["mean"]["scaled_error"] == pytest.approx(100 * (projected / actual - 1))
    assert by_stat["p10"]["scaled_error"] == pytest.approx(100 * (projected - actual) / median)
    assert by_stat["gini"]["scaled_error"] == pytest.approx(100 * (share - actual_share))
    assert np.isnan(by_stat["gini"]["pct_error"])
    assert by_stat["p50"]["error"] == 0 and by_stat["p50"]["scaled_error"] == 0


def test_a_non_positive_actual_is_scored_against_the_median():
    rows = backtest.score_rows(
        {"median_race_2": 5.0, "p50": 100.0}, {"median_race_2": -5.0, "p50": 200.0}
    )
    row = {item["stat"]: item for item in rows}["median_race_2"]
    assert np.isnan(row["pct_error"])
    assert row["scaled_error"] == pytest.approx(100 * 10.0 / 200.0)


def test_summary_scores_average_absolute_errors():
    rows = []
    for stat, value in zip(backtest.LEVEL_STATS, (-6, 6, 0, 0, 0, 0), strict=True):
        rows.append({"stat": stat, "scaled_error": value})
    for stat, value in zip(backtest.DISTRIBUTION_STATS, (1, -2, 3), strict=True):
        rows.append({"stat": stat, "scaled_error": value})
    for stat in backtest.SUBGROUP_STATS:
        rows.append({"stat": stat, "scaled_error": -5})
    rows.append({"stat": "p10", "scaled_error": 99})
    scores = pd.DataFrame(rows).assign(base=1, target=4, method="m", role="primary")
    summary = backtest.summarize(scores).set_index("score")["mean_abs_error"]
    assert summary.to_dict() == {
        "level": 2.0,
        "level_blind": 1.5,
        "distribution": 2.0,
        "subgroup": 5.0,
    }


def test_methods_are_named_once_and_four_are_primary():
    names = [method.name for method in backtest.METHODS]
    assert len(names) == len(set(names))
    primary = [method.name for method in backtest.METHODS if method.role == "primary"]
    assert primary == ["a_no_change", "b_uniform", "c_asset_class", "d_dfa_groups"]
    assert set(backtest.NOISE_METHODS) <= set(names)
    assert len(backtest.pairs(2025)) == 12 and backtest.pairs(2025)[-1] == (2022, 2025)


def test_noise_combines_the_two_standard_errors():
    scores = pd.DataFrame(
        {"base": [1], "target": [4], "method": ["m"], "stat": ["mean"], "error": [10.0]}
    )
    errors = pd.DataFrame(
        {
            "base": [1, 4],
            "target": [4, 4],
            "method": ["m", "actual"],
            "stat": ["mean", "mean"],
            "se": [3.0, 4.0],
        }
    )
    merged = backtest.add_noise(scores, errors)
    assert merged["se_error"].item() == pytest.approx(5.0)
    assert merged["z"].item() == pytest.approx(2.0)


@pytest.fixture(scope="module")
def results():
    return backtest.run(LAST_PINNED)


@pytest.mark.scf
def test_backtest_is_deterministic(results):
    again = backtest.run(LAST_PINNED)
    for first, second in zip(results, again, strict=True):
        pd.testing.assert_frame_equal(first, second, check_exact=True)


@pytest.mark.scf
def test_committed_results_match_a_fresh_run(results):
    scores, factors, waves = results
    committed = pd.read_csv(backtest.RESULTS_DIR / "scores.csv")
    columns = ["base", "target", "method", "stat", "projected", "actual", "error"]
    merged = committed[columns].merge(
        scores[columns], on=columns[:4], suffixes=("_committed", "_fresh"), validate="one_to_one"
    )
    assert len(merged) == len(scores) == len(committed)
    for column in ("projected", "actual", "error"):
        np.testing.assert_allclose(
            merged[f"{column}_committed"], merged[f"{column}_fresh"], rtol=1e-8, atol=1e-6
        )
    committed_factors = pd.read_csv(backtest.RESULTS_DIR / "factors.csv")
    np.testing.assert_allclose(committed_factors["factor"], factors["factor"], rtol=1e-8)


@pytest.mark.scf
def test_no_change_reproduces_the_base_wave(results):
    scores, _, waves = results
    actual = waves.set_index(["wave", "stat"])["value"]
    subset = scores[scores["method"] == "a_no_change"]
    for row in subset.itertuples():
        assert row.projected == pytest.approx(actual[(row.base, row.stat)], rel=1e-12)


@pytest.mark.scf
def test_uniform_methods_share_the_base_wave_distribution(results):
    scores, _, _ = results
    wide = scores[scores["stat"].isin(backtest.DISTRIBUTION_STATS)].pivot_table(
        index=["base", "stat"], columns="method", values="projected"
    )
    for method in ("b_uniform", "b_uniform_aggregate", "b_uniform_q2", "o_uniform_oracle"):
        np.testing.assert_allclose(wide[method], wide["a_no_change"], rtol=1e-9)


@pytest.mark.scf
def test_oracles_hit_the_aggregates_they_are_given(results):
    scores, _, _ = results
    mean = scores[scores["stat"] == "mean"].set_index(["base", "method"])
    for base, _ in backtest.pairs(LAST_PINNED):
        for method in ("o_uniform_oracle", "o_asset_class_oracle"):
            row = mean.loc[(base, method)]
            # Implicates differ in total weight by parts in ten million, so the
            # mean of implicate means is not exactly the stacked mean.
            assert row["projected"] == pytest.approx(row["actual"], rel=1e-6)


@pytest.mark.scf
def test_class_scaling_moves_each_class_by_its_factor_in_the_real_data(results):
    _, factors, _ = results
    base, target = backtest.pairs(LAST_PINNED)[-1]
    sheet = project.balance_sheet(scf.load_wave(base))
    table = factors[(factors["base"] == base) & (factors["method"] == "c_asset_class")]
    chosen = dict(zip(table["item"], table["factor"], strict=True))
    projected = project.scale_classes(sheet, chosen)
    assert projected["wgt"].equals(sheet["wgt"])
    for name, factor in chosen.items():
        before = float(np.sum(sheet[name] * sheet["wgt"]))
        after = float(np.sum(projected[name] * projected["wgt"]))
        assert after == pytest.approx(factor * before, rel=1e-12)


@pytest.mark.scf
def test_standard_errors_match_the_codebook_formula_on_one_wave():
    year = min(int(key) for key in scf.pins())
    sheet = project.balance_sheet(scf.load_wave(year))
    weights = replicates.load(year)
    table = replicates.standard_errors(sheet, weights)
    by_implicate = [
        stats.weighted_mean(group["networth"], group["wgt"])
        for _, group in sheet.groupby("implicate")
    ]
    first = sheet[sheet["implicate"] == 1].set_index("case")["networth"]
    matrix = weights.loc[first.index].to_numpy()
    by_replicate = (first.to_numpy()[:, None] * matrix).sum(axis=0) / matrix.sum(axis=0)
    expected = np.sqrt(6 / 5 * np.var(by_implicate, ddof=1) + np.var(by_replicate, ddof=1))
    assert table.loc["mean", "se"] == pytest.approx(expected, rel=1e-9)
    assert table.loc["mean", "estimate"] == pytest.approx(np.mean(by_implicate), rel=1e-12)
    assert (table["se"] > 0).all()
