"""The report's tables and figures build from the committed results."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import pytest

from wealthdata import backtest, report


@pytest.fixture(scope="module")
def results():
    return report.load()


def test_dollar_formatting():
    assert report.dollars(29_600) == "$29.6k"
    assert report.dollars(215_900) == "$216k"
    assert report.dollars(1_241_500) == "$1.24M"
    assert report.dollars(14_956_600) == "$15.0M"
    assert report.dollars(-1_500) == "$-1.5k"


def test_tables_cover_every_pair_and_contender(results):
    base, target = report.last_pair(results["scores"])
    pair_count = len(backtest.pairs(target))
    assert len(report.wave_table(results)) == pair_count + 1
    assert len(report.factor_table(results)) == pair_count
    scores = report.score_table(results, report.CONTENDERS)
    assert list(scores.index) == list(report.CONTENDERS.values())
    for label in report.SCORE_LABELS.values():
        assert scores[f"{label} pairs won"].sum() == pair_count
    by_pair = report.pair_score_table(results, "level", report.CONTENDERS)
    assert by_pair.shape == (len(report.CONTENDERS), pair_count)
    stats = (*backtest.LEVEL_STATS, *backtest.DISTRIBUTION_STATS)
    assert len(report.detail_table(results, base, target, stats)) == len(stats)
    assert len(report.failure_table(results, stats)) == len(stats)
    real_time = report.real_time_table(results)
    assert set(real_time["Score"]) == set(report.SCORE_LABELS.values())


def test_every_scored_error_has_a_standard_error(results):
    scores = results["scores"]
    scored = scores[scores["method"].isin(backtest.NOISE_METHODS)]
    assert scored["se_error"].notna().all() and (scored["se_error"] > 0).all()
    assert scored["z"].notna().all()


def test_published_check_reports_small_gaps(results):
    table = report.published_check(results, {2022: (211.1, 1164.1)})
    gaps = table["Gap"].str.rstrip("%").astype(float)
    assert (gaps.abs() < 1.0).all()


def test_figures_draw(results):
    base, target = report.last_pair(results["scores"])
    figure = report.headline_figure(results, base, target)
    assert len(figure.axes[0].collections) >= 2 * len(report.CONTENDERS)
    history = report.median_history_figure(results)
    assert len(history.axes[0].lines) == len(report.CONTENDERS) + 1
