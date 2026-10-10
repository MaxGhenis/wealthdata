"""Checks on the SCF extracts themselves. These download from the Fed."""

from __future__ import annotations

import numpy as np
import pytest

from wealthdata import aggregates, project, replicates, scf, stats

pytestmark = pytest.mark.scf

PINNED = sorted(int(year) for year in scf.pins())

#: All-family net worth in thousands of 2025 dollars from the Fed's report on
#: the 2025 survey (Table 2): (median, mean).
PUBLISHED = {2022: (211.1, 1164.1)}


@pytest.fixture(scope="module", params=PINNED)
def wave(request):
    return request.param, scf.load_wave(request.param)


def test_every_household_has_five_implicates_with_positive_weight(wave):
    year, frame = wave
    assert (frame.groupby("case")["implicate"].apply(sorted).map(tuple) == (1, 2, 3, 4, 5)).all()
    assert (frame["wgt"] > 0).all()
    totals = frame.groupby("implicate")["wgt"].sum()
    assert totals.max() / totals.min() - 1 < 1e-5


def test_seven_classes_sum_to_the_extract_net_worth(wave):
    year, frame = wave
    sheet = project.balance_sheet(frame)
    assert (sheet["networth"] - frame["networth"]).abs().max() < 1.0
    assert (sheet[list(project.ASSET_CLASSES)].sum(axis=1) - frame["asset"]).abs().max() < 1.0
    for name in ("equities", "deposits", "debt"):
        assert (sheet[name] >= 0).all()
    # A few households carry houses = -1, a code the macro leaves unscaled.
    assert (sheet["housing"] >= -1).all()
    assert (sheet["housing"] < 0).sum() <= 20


def test_weights_sum_to_about_the_census_household_count(wave):
    year, frame = wave
    families = frame["wgt"].sum() / 1000
    assert families == pytest.approx(aggregates.households()[year], rel=0.03)


def test_demographic_codes_are_the_documented_ones(wave):
    year, frame = wave
    assert set(frame["agecl"]) == set(scf.AGE_LABELS)
    assert set(frame["racecl4"]) == set(scf.RACE_LABELS)


@pytest.mark.parametrize("year", sorted(PUBLISHED))
def test_public_extract_is_close_to_the_published_figures(year):
    if year not in PINNED:
        pytest.skip(f"the {year} extract is not pinned")
    frame = scf.load_wave(year)
    median, mean = PUBLISHED[year]
    # The public file drops Forbes-level respondents and rounds values, so it
    # sits slightly below the internal file the report is built from.
    assert stats.weighted_mean(frame["networth"], frame["wgt"]) / 1e3 == pytest.approx(
        mean, rel=0.01
    )
    assert stats.weighted_quantile(frame["networth"], frame["wgt"], 0.5) / 1e3 == pytest.approx(
        median, rel=0.01
    )


def test_an_unpinned_wave_cannot_be_loaded(monkeypatch):
    monkeypatch.setattr(scf, "pins", lambda: {})
    with pytest.raises(PermissionError):
        scf.load_wave(1989)
    monkeypatch.setattr(replicates, "pins", lambda: {})
    with pytest.raises(PermissionError):
        replicates.load(1989)


def test_replicate_weights_cover_the_sample_and_the_population(wave):
    year, frame = wave
    weights = replicates.load(year)
    assert weights.shape[1] == replicates.REPLICATE_COUNT
    assert set(weights.index) == set(frame["case"])
    totals = weights.sum(axis=0)
    # The codebook: each replicate's weights sum to the number of households.
    np.testing.assert_allclose(totals, frame["wgt"].sum(), rtol=2e-3)
