# wealthdata

A backtest of aging US wealth microdata between survey waves.

The Survey of Consumer Finances (SCF) comes out every three years. Models that
need current wealth take the latest wave and grow it with aggregates from the
Federal Reserve's Financial Accounts (Z.1). This repository measures how well
that works: it projects every SCF wave from 1989 to 2022 three years forward
and scores each projection against the wave that followed, ending with the
2025 survey published on 9 October 2026.

This repository began in 2019 as a proposal to project the SCF forward on
quarterly household net worth from the Financial Accounts
(`BOGZ1FL192090005Q`). No code was written then. Method (b) below is that
proposal.

## Result

The design in [PREREGISTRATION.md](PREREGISTRATION.md) was frozen and tagged
`prereg-v1` before the 2025 microdata were opened. The report is
[report/report.md](report/report.md) (also a self-contained
[report/report.html](report/report.html)); the headline:

- On 2022→2025, aging helped on levels. The lowest level error, over the mean
  and five percentiles, was DFA wealth-group scaling at 5.6% against 8.8% for
  doing nothing; on the four percentiles whose 2025 values were unpublished
  at the freeze, asset-class scaling won at 5.9% against 11.1%.
- Every aging method overshot the 2025 mean by 7% to 9%. Financial Accounts
  equities grew 54% in real terms per household from 2022 to 2025; mean SCF
  equity holdings grew 20%.
- No method caught the fall in the top 1% share, from 35.1% to 31.3%, and on
  medians by age and race doing nothing beat every aging method.
- Over all twelve pairs, asset-class scaling had the lowest mean level error
  of the methods that use nothing from the target wave, 10.7% against 13.8%
  for doing nothing, but beat doing nothing on only 7 of 12 pairs.

## Methods

| | Method | What it does |
| --- | --- | --- |
| (a) | No change | Holds real dollar amounts fixed |
| (b) | Uniform | Scales everything by real household net worth growth per household |
| (c) | Asset class | Scales equities, deposits, other financial assets, housing, business, other nonfinancial assets and debt by their own Financial Accounts series |
| (d) | DFA groups | Scales each wealth group's assets and debt by that group's growth in the Distributional Financial Accounts |

Every method leaves weights and demographics untouched.

## Run it

```bash
uv sync
uv run pytest
uv run python -m wealthdata.backtest
```

The first run downloads the SCF extracts and replicate weights from the
Federal Reserve (about 390 MB) into `~/.cache/wealthdata`; set
`WEALTHDATA_CACHE` to put them elsewhere. Aggregate inputs are committed under
`data/aggregates/`, so results do not move when the Fed revises a series.
`uv run python -m wealthdata.sources` rebuilds that snapshot from the live
sources.

## Layout

- `src/wealthdata/scf.py`: SCF extract loader with pinned file hashes.
- `src/wealthdata/aggregates.py`: growth factors from the committed snapshot.
- `src/wealthdata/project.py`: the projection methods.
- `src/wealthdata/stats.py`: weighted quantiles, top shares, Gini coefficient.
- `src/wealthdata/replicates.py`: standard errors from the SCF replicate weights.
- `src/wealthdata/backtest.py`: runs every wave pair and writes `results/`.
- `src/wealthdata/report.py`: tables and figures built from `results/`.
- `docs/sources.md`: where each claim about the source data was read.

## License

MIT for the code. The data are US government works: the SCF, Financial
Accounts and DFA from the Federal Reserve Board and the household count from
the Census Bureau. Some were retrieved through FRED and ALFRED (Federal Reserve
Bank of St. Louis), which list them as public domain, citation requested.
