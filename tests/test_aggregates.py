"""Checks on the aggregate snapshots and the factors built from them."""

from __future__ import annotations

import itertools
import json

import pytest

from wealthdata import aggregates, project, scf, sources

WAVE_TRIPLES = list(itertools.combinations(scf.WAVES, 3))


def test_cpi_values_are_the_bulletin_macro_values():
    assert aggregates.cpi_u_rs() == {
        1989: 1898,
        1992: 2112,
        1995: 2261,
        1998: 2400,
        2001: 2614,
        2004: 2785,
        2007: 3058,
        2010: 3204,
        2013: 3438,
        2016: 3548,
        2019: 3775,
        2022: 4376,
        2025: 4789,
    }


def test_cpi_parser_reads_the_macro_layout():
    macro = """
  %IF (&YEAR=1989) %THEN %DO;
    %LET CPIADJ=&CPIBASE/1898;
    %LET CPILAG=1883/1805;
  %END;
  %ELSE %IF (&YEAR=1992) %THEN %DO;
    %LET CPIADJ=&CPIBASE/2112;
    """
    assert sources.parse_cpi_u_rs(macro) == {1989: 1898, 1992: 2112}
    with pytest.raises(ValueError):
        sources.parse_cpi_u_rs("no blocks here")


@pytest.mark.parametrize("base,middle,target", WAVE_TRIPLES[::7])
def test_factors_chain_across_waves(base, middle, target):
    assert aggregates.price_ratio(base, target) == pytest.approx(
        aggregates.price_ratio(base, middle) * aggregates.price_ratio(middle, target)
    )
    assert aggregates.household_ratio(base, target) == pytest.approx(
        aggregates.household_ratio(base, middle) * aggregates.household_ratio(middle, target)
    )
    assert aggregates.net_worth_factor(base, target) == pytest.approx(
        aggregates.net_worth_factor(base, middle) * aggregates.net_worth_factor(middle, target)
    )
    whole = aggregates.class_factors(base, target)
    first, second = aggregates.class_factors(base, middle), aggregates.class_factors(middle, target)
    for name in project.CLASSES:
        assert whole[name] == pytest.approx(first[name] * second[name])


@pytest.mark.parametrize("year", scf.WAVES)
def test_a_wave_projected_onto_itself_is_unchanged(year):
    assert aggregates.net_worth_factor(year, year) == 1.0
    assert set(aggregates.class_factors(year, year).values()) == {1.0}
    assert set(aggregates.dfa_group_factors(year, year).values()) == {1.0}


@pytest.mark.parametrize("base", scf.WAVES[:-1])
def test_household_adjustment_is_exactly_household_growth(base):
    target = base + 3
    aggregate = aggregates.net_worth_factor(base, target, per_household=False)
    per_household = aggregates.net_worth_factor(base, target)
    assert aggregate / per_household == pytest.approx(aggregates.household_ratio(base, target))
    assert 0.95 < aggregates.household_ratio(base, target) < 1.10
    assert 1.0 < aggregates.price_ratio(base, target) < 1.20


def test_every_class_has_a_series_for_every_wave_and_quarter():
    assert set(aggregates.CLASS_SERIES) == set(project.CLASSES)
    table = aggregates.z1()
    for year in scf.WAVES:
        for quarter in (2, 3, 4):
            row = table.loc[aggregates.label(year, quarter)]
            for series in aggregates.CLASS_SERIES.values():
                assert row[list(series)].notna().all()
                assert (row[list(series)] > 0).all()


def test_financial_accounts_identities_hold_in_the_snapshot():
    table = aggregates.z1()
    parts = table[
        ["FL154000005", "FL153034005", "LM154022375", "FL154035005", "LM153064475", "FL153099475"]
    ].sum(axis=1)
    # Published in millions; components can each round by half a million.
    assert (parts - table["FL154090005"]).abs().max() <= 3
    net_worth = table["FL152000005"] - table["FL154190005"]
    assert (net_worth - table["FL152090005"]).abs().max() <= 1


def test_dfa_groups_sum_to_household_net_worth():
    """Two independent downloads agree: the DFA file and FRED's Z.1 series."""
    total = aggregates.dfa("current").sum(axis=1)
    households = aggregates.household_net_worth()
    common = total.index.intersection(households.index)
    assert len(common) >= 148
    assert ((total[common] / households[common]) - 1).abs().max() < 1e-3


def test_dfa_vintages_cover_their_wave_pairs():
    current = aggregates.dfa("current")
    assert list(current.columns) == sorted(project.DFA_GROUPS_5)
    for year in scf.WAVES:
        assert aggregates.label(year) in current.index
    for target, vintage in aggregates.DFA_REAL_TIME_VINTAGE.items():
        table = aggregates.dfa(vintage)
        assert aggregates.label(target) in table.index
        assert aggregates.label(target - 3) in table.index
        factors = aggregates.dfa_group_factors(target - 3, target, vintage=vintage)
        assert all(value > 0 for value in factors.values())
    assert list(aggregates.dfa("alfred_20200630").columns) == sorted(project.DFA_GROUPS_4)


def test_merged_top_group_is_the_sum_of_its_parts():
    table = aggregates.dfa("current")
    factors = aggregates.dfa_group_factors(2016, 2019, groups=tuple(project.DFA_GROUPS_4))
    top = table["TopPt1"] + table["RemainingTop1"]
    nominal = top["2019-Q3"] / top["2016-Q3"]
    assert factors["Top1"] == pytest.approx(aggregates.real_per_household(nominal, 2016, 2019))


def test_real_time_vintages_predate_the_target_scf_release():
    """Snapshots used as real-time inputs were published before the target SCF."""
    manifest = json.loads((sources.AGGREGATES_DIR / "MANIFEST.json").read_text())
    current = manifest["dfa_networth_levels_current.csv"]["source_last_modified"]
    assert current == "Fri, 18 Sep 2026 19:35:02 GMT"  # the 2025 SCF came out 9 October 2026
    assert "20230922" in manifest["dfa_networth_levels_wayback_20230922.csv"]["url"]
    for target, vintage in aggregates.NET_WORTH_REAL_TIME_VINTAGE.items():
        assert vintage == f"{target + 1}-06-30"
        levels = aggregates.household_net_worth(vintage)
        assert aggregates.label(target) in levels.index
        assert aggregates.label(target + 1, 3) not in levels.index


def test_manifest_hashes_match_the_committed_files():
    manifest = json.loads((sources.AGGREGATES_DIR / "MANIFEST.json").read_text())
    for name, entry in manifest.items():
        assert sources.sha256((sources.AGGREGATES_DIR / name).read_bytes()) == entry["sha256"]
