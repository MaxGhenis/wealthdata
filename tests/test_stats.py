"""Properties of the weighted statistics, and agreement with reference code."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from conftest import amounts, factors, samples
from wealthdata import stats

quantile_levels = st.floats(min_value=0.01, max_value=1.0)


def reference_gini(x: np.ndarray, w: np.ndarray) -> float:
    """Mean absolute difference between two draws over twice the mean."""
    differences = np.abs(x[:, None] - x[None, :])
    total = np.sum(w)
    mean = np.sum(x * w) / total
    return float(np.sum(w[:, None] * w[None, :] * differences) / (2 * mean * total**2))


def reference_top_share(x: np.ndarray, w: np.ndarray, fraction: float) -> float:
    """Walk down from the richest household, splitting the one at the cutoff."""
    order = np.argsort(-x, kind="stable")
    budget = fraction * np.sum(w)
    held = 0.0
    for value, weight in zip(x[order], w[order], strict=True):
        take = min(weight, budget)
        held += take * value
        budget -= take
        if budget <= 0:
            break
    return float(held / np.sum(x * w))


@given(samples(), quantile_levels)
def test_quantile_matches_numpy_inverted_cdf(sample, q):
    x, w = sample
    expected = np.quantile(x, q, weights=w, method="inverted_cdf")
    assert stats.weighted_quantile(x, w, q) == pytest.approx(expected, rel=1e-12, abs=1e-12)


@given(
    st.lists(st.tuples(st.integers(-1000, 1000), st.integers(1, 6)), min_size=1, max_size=30),
    quantile_levels,
)
def test_quantile_with_integer_weights_equals_repeated_observations(pairs, q):
    x = np.array([value for value, _ in pairs], dtype=float)
    w = np.array([count for _, count in pairs], dtype=float)
    repeated = np.repeat(x, w.astype(int))
    expected = np.quantile(repeated, q, method="inverted_cdf")
    assert stats.weighted_quantile(x, w, q) == expected


@given(samples(), quantile_levels, quantile_levels)
def test_quantile_is_an_observation_and_monotone_in_q(sample, q1, q2):
    x, w = sample
    low, high = sorted((q1, q2))
    a, b = stats.weighted_quantile(x, w, low), stats.weighted_quantile(x, w, high)
    assert a in x and b in x
    assert a <= b


@given(samples(), quantile_levels, factors)
def test_quantile_and_mean_scale_with_the_values(sample, q, factor):
    x, w = sample
    assert stats.weighted_quantile(x * factor, w, q) == pytest.approx(
        factor * stats.weighted_quantile(x, w, q), rel=1e-12, abs=1e-9
    )
    assert stats.weighted_mean(x * factor, w) == pytest.approx(
        factor * stats.weighted_mean(x, w), rel=1e-9, abs=1e-6
    )


@given(samples(min_size=2, values=amounts))
def test_gini_matches_mean_difference_formula(sample):
    x, w = sample
    assume(np.sum(x * w) > 1e-3)
    assert stats.gini(x, w) == pytest.approx(reference_gini(x, w), rel=1e-9, abs=1e-9)


@given(samples(min_size=2))
def test_gini_matches_mean_difference_formula_with_negative_values(sample):
    x, w = sample
    assume(np.sum(x * w) > 1e-3 * np.sum(np.abs(x) * w) > 0)
    assert stats.gini(x, w) == pytest.approx(reference_gini(x, w), rel=1e-7, abs=1e-7)


@given(samples(min_size=2, values=amounts))
def test_gini_is_between_zero_and_one_for_nonnegative_values(sample):
    x, w = sample
    assume(np.sum(x * w) > 1e-3)
    assert -1e-12 <= stats.gini(x, w) < 1


@given(amounts, st.lists(st.floats(min_value=0.5, max_value=5e4), min_size=1, max_size=20))
def test_gini_is_zero_when_everyone_holds_the_same(value, w):
    assume(value > 1e-3)
    assert stats.gini(np.full(len(w), value), np.array(w)) == pytest.approx(0, abs=1e-12)


@given(samples(min_size=2, values=amounts), st.floats(min_value=0.001, max_value=0.999))
def test_top_share_matches_direct_accumulation(sample, fraction):
    x, w = sample
    assume(np.sum(x * w) > 1e-3)
    assert stats.top_share(x, w, fraction) == pytest.approx(
        reference_top_share(x, w, fraction), rel=1e-7, abs=1e-7
    )


@given(
    samples(min_size=2, values=amounts),
    st.floats(min_value=0.001, max_value=0.999),
    st.floats(min_value=0.001, max_value=0.999),
)
def test_top_share_bounds_and_monotonicity(sample, f1, f2):
    x, w = sample
    assume(np.sum(x * w) > 1e-3)
    low, high = sorted((f1, f2))
    share_low, share_high = stats.top_share(x, w, low), stats.top_share(x, w, high)
    assert share_low <= share_high + 1e-12
    # The richest fraction f holds at least a share f of a nonnegative total.
    assert share_low >= low - 1e-9
    assert share_high <= 1 + 1e-12


@given(samples(min_size=2), factors, st.floats(min_value=0.01, max_value=100))
def test_shares_and_gini_ignore_units_and_weight_scale(sample, factor, weight_scale):
    x, w = sample
    assume(np.sum(x * w) > 1e-3 * np.sum(np.abs(x) * w) > 0)
    for statistic in (stats.gini, lambda a, b: stats.top_share(a, b, 0.1)):
        base = statistic(x, w)
        assert statistic(x * factor, w) == pytest.approx(base, rel=1e-7, abs=1e-7)
        assert statistic(x, w * weight_scale) == pytest.approx(base, rel=1e-7, abs=1e-7)


@given(samples(min_size=2), st.integers(0, 39))
def test_splitting_a_household_in_two_changes_nothing(sample, index):
    x, w = sample
    assume(np.sum(x * w) > 1e-3 * np.sum(np.abs(x) * w) > 0)
    index %= x.size
    x2 = np.append(x, x[index])
    w2 = np.append(w, w[index] / 2)
    w2[index] /= 2
    assert stats.weighted_mean(x2, w2) == pytest.approx(stats.weighted_mean(x, w), rel=1e-9)
    assert stats.gini(x2, w2) == pytest.approx(stats.gini(x, w), rel=1e-7, abs=1e-7)
    assert stats.top_share(x2, w2, 0.1) == pytest.approx(
        stats.top_share(x, w, 0.1), rel=1e-7, abs=1e-7
    )


def test_known_values():
    x, w = np.array([0.0, 1.0]), np.array([1.0, 1.0])
    assert stats.gini(x, w) == pytest.approx(0.5)
    assert stats.top_share(x, w, 0.5) == pytest.approx(1.0)
    assert stats.top_share(x, w, 0.25) == pytest.approx(0.5)
    values, counts = np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 2.0])
    assert stats.weighted_quantile(values, counts, 0.5) == 2.0
    assert stats.weighted_quantile(values, counts, 0.51) == 3.0


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        stats.weighted_quantile([1.0, 2.0], [1.0, 0.0], 0.5)
    with pytest.raises(ValueError):
        stats.weighted_quantile([1.0, 2.0], [1.0, 1.0], 0.0)
    with pytest.raises(ValueError):
        stats.gini([-1.0, 0.5], [1.0, 1.0])
    with pytest.raises(ValueError):
        stats.weighted_mean([], [])


def test_across_implicates_averages_per_implicate_estimates():
    frame = pd.DataFrame(
        {
            "implicate": [1, 1, 2, 2],
            "networth": [0.0, 10.0, 0.0, 30.0],
            "wgt": [1.0, 1.0, 1.0, 1.0],
            "agecl": [1, 1, 1, 1],
            "racecl4": [1, 1, 1, 1],
        }
    )
    averaged = stats.across_implicates(frame)
    assert averaged["mean"] == pytest.approx(10.0)
    assert averaged["p90"] == pytest.approx(20.0)
    assert stats.pooled(frame)["p90"] == pytest.approx(30.0)
    assert stats.pooled(frame)["mean"] == pytest.approx(averaged["mean"])
