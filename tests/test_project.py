"""Invariants of the projection methods.

The four named in the study design come first: uniform scaling leaves the
Gini coefficient and top shares unchanged; class scaling reproduces each
class's aggregate growth exactly; projections are deterministic; weights are
untouched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from conftest import class_factor_maps, factors, sheets
from wealthdata import project, stats

group_factor_maps = st.fixed_dictionaries(
    {name: class_factor_maps for name in project.DFA_GROUPS_5}
)

PROJECTIONS = st.one_of(
    st.just(project.no_change),
    factors.map(lambda f: lambda sheet: project.scale_uniform(sheet, f)),
    class_factor_maps.map(lambda m: lambda sheet: project.scale_classes(sheet, m)),
    group_factor_maps.map(
        lambda m: lambda sheet: project.scale_wealth_groups(sheet, m, project.DFA_GROUPS_5)
    ),
)


def _total(sheet: pd.DataFrame, column: str) -> float:
    return float(np.sum(sheet[column] * sheet["wgt"]))


def _has_stable_shares(sheet: pd.DataFrame) -> bool:
    """Shares exist only for a positive total, and are well conditioned only
    when that total is not a near-cancellation of positive and negative worth.
    Checked per implicate, because statistics are computed per implicate."""
    for _, implicate in sheet.groupby("implicate"):
        gross = float(np.sum(implicate["networth"].abs() * implicate["wgt"]))
        if not (gross > 0 and _total(implicate, "networth") > 1e-3 * gross):
            return False
    return True


@given(sheets(), factors)
def test_uniform_scaling_leaves_gini_and_top_shares_unchanged(sheet, factor):
    assume(_has_stable_shares(sheet))
    projected = project.scale_uniform(sheet, factor)
    for _, before in sheet.groupby("implicate"):
        after = projected.loc[before.index]
        x0, x1, w = before["networth"], after["networth"], before["wgt"]
        assert stats.gini(x1, w) == pytest.approx(stats.gini(x0, w), rel=1e-6, abs=1e-6)
        for fraction in (0.10, 0.01):
            assert stats.top_share(x1, w, fraction) == pytest.approx(
                stats.top_share(x0, w, fraction), rel=1e-6, abs=1e-6
            )


@given(sheets(), factors)
def test_uniform_scaling_multiplies_every_dollar_statistic(sheet, factor):
    projected = project.scale_uniform(sheet, factor)
    scale = float(np.max(np.abs(sheet[list(project.CLASSES)].to_numpy()))) + 1.0
    np.testing.assert_allclose(
        projected["networth"], factor * sheet["networth"], rtol=1e-9, atol=1e-9 * scale
    )
    assert stats.weighted_mean(projected["networth"], projected["wgt"]) == pytest.approx(
        factor * stats.weighted_mean(sheet["networth"], sheet["wgt"]), rel=1e-9, abs=1e-9 * scale
    )


@given(sheets(), class_factor_maps)
def test_class_scaling_reproduces_each_class_aggregate_growth(sheet, class_factors):
    projected = project.scale_classes(sheet, class_factors)
    for name, factor in class_factors.items():
        assert _total(projected, name) == pytest.approx(
            factor * _total(sheet, name), rel=1e-12, abs=1e-6
        )
        np.testing.assert_array_equal(projected[name], sheet[name] * factor)
    expected = sum(class_factors[name] * _total(sheet, name) for name in project.ASSET_CLASSES)
    expected -= class_factors["debt"] * _total(sheet, "debt")
    scale = sum(abs(_total(sheet, name)) for name in project.CLASSES) + 1.0
    assert _total(projected, "networth") == pytest.approx(expected, rel=1e-9, abs=1e-9 * scale)


@given(sheets(), PROJECTIONS, st.randoms(use_true_random=False))
def test_projections_are_deterministic_and_ignore_row_order(sheet, method, random):
    first = method(sheet)
    pd.testing.assert_frame_equal(first, method(sheet), check_exact=True)
    # Shuffle households within each implicate; ties in net worth are broken
    # by input order, so only compare when net worth is unique per implicate.
    assume(not sheet.duplicated(["implicate", "networth"]).any())
    order = list(sheet.index)
    random.shuffle(order)
    shuffled = method(sheet.loc[order])
    pd.testing.assert_frame_equal(shuffled.loc[sheet.index], first, check_exact=True)


@given(sheets(), PROJECTIONS)
def test_weights_and_households_are_untouched(sheet, method):
    original = sheet.copy(deep=True)
    projected = method(sheet)
    pd.testing.assert_frame_equal(sheet, original, check_exact=True)
    for column in project.FIXED_COLUMNS:
        pd.testing.assert_series_equal(projected[column], original[column], check_exact=True)
    assert list(projected.columns) == list(original.columns)
    assert projected.index.equals(original.index)


@given(sheets(), PROJECTIONS)
def test_balance_sheet_identity_holds_after_projection(sheet, method):
    projected = method(sheet)
    np.testing.assert_array_equal(projected["networth"], project.net_worth(projected))


@given(sheets())
def test_no_change_and_unit_factors_are_the_identity(sheet):
    pd.testing.assert_frame_equal(project.no_change(sheet), sheet, check_exact=True)
    pd.testing.assert_frame_equal(project.scale_uniform(sheet, 1.0), sheet, check_exact=True)
    ones = dict.fromkeys(project.CLASSES, 1.0)
    pd.testing.assert_frame_equal(project.scale_classes(sheet, ones), sheet, check_exact=True)
    unit_groups = dict.fromkeys(project.DFA_GROUPS_5, ones)
    pd.testing.assert_frame_equal(
        project.scale_wealth_groups(sheet, unit_groups, project.DFA_GROUPS_5),
        sheet,
        check_exact=True,
    )


@given(sheets(), factors)
def test_equal_factors_reduce_to_uniform_scaling(sheet, factor):
    uniform = project.scale_uniform(sheet, factor)
    equal = dict.fromkeys(project.CLASSES, factor)
    by_class = project.scale_classes(sheet, equal)
    by_group = project.scale_wealth_groups(
        sheet, dict.fromkeys(project.DFA_GROUPS_4, equal), project.DFA_GROUPS_4
    )
    pd.testing.assert_frame_equal(by_class, uniform, check_exact=True)
    pd.testing.assert_frame_equal(by_group, uniform, check_exact=True)
    assert project.assets_and_debt(factor, factor) == equal


@given(sheets(), class_factor_maps)
def test_identical_group_factors_reduce_to_class_scaling(sheet, class_factors):
    by_class = project.scale_classes(sheet, class_factors)
    by_group = project.scale_wealth_groups(
        sheet, dict.fromkeys(project.DFA_GROUPS_5, class_factors), project.DFA_GROUPS_5
    )
    pd.testing.assert_frame_equal(by_group, by_class, check_exact=True)


@given(sheets(), factors, factors)
def test_uniform_scalings_compose(sheet, first, second):
    twice = project.scale_uniform(project.scale_uniform(sheet, first), second)
    once = project.scale_uniform(sheet, first * second)
    scale = float(np.max(np.abs(sheet[list(project.CLASSES)].to_numpy()))) + 1.0
    np.testing.assert_allclose(
        twice[list(project.CLASSES)], once[list(project.CLASSES)], rtol=1e-12, atol=1e-12 * scale
    )


@given(sheets(min_households=5, max_households=60, implicate_count=1), group_factor_maps)
def test_wealth_groups_partition_households_in_rank_order(sheet, group_factors):
    bounds = project.DFA_GROUPS_5
    groups = project.wealth_group(sheet["networth"], sheet["wgt"], bounds)
    names = list(bounds)
    assert set(groups) <= set(names)
    rank = np.array([names.index(name) for name in groups])
    order = np.argsort(sheet["networth"].to_numpy(), kind="stable")
    assert np.all(np.diff(rank[order]) >= 0)
    # Each group's weight share is within one household of its target share.
    total = sheet["wgt"].sum()
    largest = sheet["wgt"].max() / total
    lower = 0.0
    cumulative = 0.0
    for name in names:
        cumulative += sheet["wgt"].to_numpy()[groups == name].sum() / total
        assert abs(cumulative - bounds[name]) <= largest + 1e-12
        assert bounds[name] > lower
        lower = bounds[name]
    projected = project.scale_wealth_groups(sheet, group_factors, bounds)
    for name in names:
        member = groups == name
        for item in project.CLASSES:
            factor = group_factors[name][item]
            np.testing.assert_array_equal(
                projected.loc[member, item], sheet.loc[member, item] * factor
            )
            # The group's weighted total of the class grows by exactly its factor.
            before = float(np.sum(sheet.loc[member, item] * sheet.loc[member, "wgt"]))
            after = float(np.sum(projected.loc[member, item] * sheet.loc[member, "wgt"]))
            assert after == pytest.approx(factor * before, rel=1e-12, abs=1e-6)


def test_wealth_group_boundaries_on_a_known_sample():
    networth = np.arange(1000, dtype=float)
    weights = np.ones(1000)
    groups = project.wealth_group(networth, weights, project.DFA_GROUPS_5)
    counts = pd.Series(groups).value_counts()
    assert counts.to_dict() == {
        "Bottom50": 500,
        "Next40": 400,
        "Next9": 90,
        "RemainingTop1": 9,
        "TopPt1": 1,
    }
    assert groups[499] == "Bottom50" and groups[500] == "Next40" and groups[999] == "TopPt1"


def test_invalid_factors_are_rejected():
    sheet = pd.DataFrame(
        {
            "case": [1],
            "implicate": np.array([1], dtype="int8"),
            "wgt": [1.0],
            "agecl": np.array([1], dtype="int8"),
            "racecl4": np.array([1], dtype="int8"),
            **dict.fromkeys(project.CLASSES, [1.0]),
        }
    )
    sheet["networth"] = project.net_worth(sheet)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            project.scale_uniform(sheet, bad)
    with pytest.raises(ValueError):
        project.scale_classes(sheet, {"equities": 1.0})
    ones = dict.fromkeys(project.CLASSES, 1.0)
    with pytest.raises(ValueError):
        project.scale_wealth_groups(sheet, {"Bottom50": ones}, project.DFA_GROUPS_5)
    with pytest.raises(ValueError):
        project.scale_wealth_groups(
            sheet, dict.fromkeys(project.DFA_GROUPS_4, {"debt": 1.0}), project.DFA_GROUPS_4
        )
