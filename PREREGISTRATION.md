# Pre-specified design: aging SCF wealth between waves

Frozen before the 2025 Survey of Consumer Finances microdata were opened. The
commit that adds this file is tagged `prereg-v1`. Anything changed after that
tag is listed under [Deviations](#deviations).

## Question

Microsimulation models hold a wealth survey that is up to three years old and
bring it to the current year with aggregate growth from the Federal Reserve's
Financial Accounts (Z.1). How close does that get to what the next survey
finds? Each SCF wave from 1989 to 2022 is projected three years forward and
scored against the wave that followed. The 2025 wave, published 9 October
2026, is the one target not used while building the methods.

## Data

**SCF.** Summary Extract Public Data for the thirteen waves 1989 to 2025
(`scfp{year}s.zip`). The Fed reissued all thirteen files on 9 October 2026 in
2025 dollars, so every wave is in the same real dollars. The macro that builds
the extract deflates assets and debts by the September CPI-U-RS of the survey
year (`bulletin.macro.txt`, `CPIADJ`). Each file's SHA-256 is pinned in
`data/scf_extracts.json`, and the loader refuses a wave that is not pinned. At
this tag the 2025 file is not pinned and has not been downloaded.

**Unit and weights.** The SCF family, weighted by `wgt` (the survey weight
divided by five). Weights and demographics are never changed.

**Aggregates.** A snapshot committed under `data/aggregates/`, with source
URLs, retrieval times and hashes in `MANIFEST.json`:

| Input | Source | As published |
| --- | --- | --- |
| Household balance sheet series, quarterly | Z.1 CSV bundle, tables S1M.b and S1M.e.b | 11 Sep 2026 |
| Households; net worth (`BOGZ1FL192090005Q`) | FRED | 11 Sep 2026 |
| The same series as of 30 June 2020, 2023, 2026 | ALFRED | vintage dates |
| Households (`TTLHH`, CPS ASEC) | FRED | 4 Dec 2025 |
| September CPI-U-RS by survey year | Fed bulletin macro | 9 Oct 2026 |
| DFA net worth, assets and liabilities by wealth group | Fed DFA download | 18 Sep 2026 |
| DFA, earlier vintages | Internet Archive (22 Sep 2023), ALFRED (30 Jun 2020) | as dated |

Financial Accounts levels are the September 2026 vintage for every pair, so
historical pairs use revised data that a forecaster at the time did not have.
`b_uniform_real_time` shows the effect for the three most recent targets.

## Growth factors

A factor turns a wave-*t* real dollar amount per household into its projected
wave-*t+3* amount in the same real dollars:

    factor = (A[t+3] / A[t]) / (H[t+3] / H[t]) / (P[t+3] / P[t])

- `A` is a nominal aggregate at the end of the third quarter of the survey
  year. SCF interviews run from spring to the turn of the year, and the Fed
  deflates with the September price level.
- `H` is the number of households (`TTLHH`). Weights stay at their wave-*t*
  values, so dollar amounts must grow per household.
- `P` is the September CPI-U-RS the Fed uses for the extract.

## Methods

Four contenders. Each multiplies dollar amounts and leaves everything else
alone.

**(a) No change.** Real dollar amounts are held fixed.

**(b) Uniform scaling.** Every amount is multiplied by the factor for
aggregate household net worth, `BOGZ1FL192090005Q`, the series named in this
repository's 2019 README.

**(c) Asset-class scaling.** Net worth is split into seven classes that sum to
it exactly. Each class is multiplied by the factor for its Financial Accounts
series:

| Class | SCF extract variables | Financial Accounts series |
| --- | --- | --- |
| Equities | `equity` | `LM153064475` directly and indirectly held corporate equities |
| Deposits | `liq + cds` | `FL154000005 + FL153034005` currency and deposits, money market fund shares |
| Other financial | `fin - equity - liq - cds` | `LM154022375` directly and indirectly held debt securities |
| Housing | `houses + oresre` | `LM155035015` owner-occupied real estate |
| Business | `bus + nnresre` | `LM153081115` other equity (within 0.12% of proprietors' equity in noncorporate business in every quarter) |
| Other nonfinancial | `nfin - houses - oresre - bus - nnresre` | `LM155111005` consumer durable goods |
| Debt | `debt` | `FL154190005` total liabilities |

The Financial Accounts series cover households and nonprofit organizations,
except owner-occupied real estate, which is households only. Known mismatches,
accepted as part of the method: SCF business equity includes closely held
corporations, which the Financial Accounts count as corporate equities; since
2007 `equity` includes savings accounts invested in stocks, which `liq` also
counts, so "other financial" is negative for a few households.

**(d) DFA wealth groups.** Households are ranked by net worth within each
implicate and placed in the DFA's groups (bottom 50%, 50th to 90th, 90th to
99th, 99th to 99.9th, top 0.1%) by the midpoint of the weight interval they
occupy. Every asset class is multiplied by the factor for the group's DFA
total assets, and debt by the factor for the group's DFA total liabilities. A
group is a fixed share of households, so its household count grows at the
national rate.

The DFA allocates Financial Accounts totals with SCF shares, interpolating
between surveys and forecasting beyond the latest one (DFA overview page). The
current vintage therefore already contains every wave through 2022, and (d) on
pairs through 2019→2022 is scored against data it was built from. Those scores
are labelled in-sample. The 18 September 2026 file predates the 2025 SCF, so
2022→2025 is a forecast.

### Pre-listed variants

Run and reported, but not contenders:

- `b_uniform_aggregate`: (b) without the household adjustment.
- `b_uniform_q2`, `b_uniform_q4`, `c_asset_class_q2`, `c_asset_class_q4`:
  second- and fourth-quarter levels.
- `b_uniform_nonprofits`: (b) with households and nonprofits net worth
  (`FL152090005`).
- `b_uniform_real_time`: (b) with the series as it stood on 30 June after the
  target wave, for targets 2019, 2022 and 2025.
- `d_dfa_groups_net_worth`: (d) with one factor per group, from the group's
  DFA net worth, applied to assets and debt alike. This was the first
  specification of (d); see "What was known".
- `d_dfa_groups_top1`: (d) with the top 1% as one group.
- `d_dfa_groups_real_time`: (d) with the vintage that stood before the target
  SCF was published: ALFRED 30 June 2020 for 2016→2019 (four groups; the
  top 0.1% split came later), Internet Archive 22 September 2023 for
  2019→2022, and the current file for 2022→2025. This is the fair record of
  the DFA method.

### Diagnostics that use the target wave

Two oracles bound what aggregate scaling could do with perfect aggregates.
They are not forecasts.

- `o_uniform_oracle`: uniform scaling by the SCF's own growth in mean net
  worth.
- `o_asset_class_oracle`: class scaling by the SCF's own growth in each class
  mean.

## Scoring

**Statistics.** Mean; 10th, 25th, 50th, 75th, 90th and 99th percentiles; top
10% and top 1% shares; Gini coefficient; median by age of the reference person
(under 35, 35-44, 45-54, 55-64, 65-74, 75 or older) and by race and ethnicity
(`racecl4`: White non-Hispanic, Black non-Hispanic, Hispanic, other or
multiple race). All of net worth.

**Definitions.** A quantile is the smallest observed value whose cumulative
weight share reaches the level, the definition in the SCF codebook's `MEANIT`
program. A top share splits the household at the cutoff in proportion to its
weight. The Gini coefficient is one minus twice the area under the Lorenz
curve.

**Implicates.** Each statistic is computed on each of the five implicates and
averaged, as `MEANIT` does. Projections are applied to each implicate. As a
check, everything is also computed with the five implicates stacked, which the
codebook calls sufficient for simple statistics.

**Errors.** Error is projected minus actual. Dollar statistics are scored in
percent of the actual value. The 10th percentile sits near zero, so it is
scored in percent of the actual median and kept out of the summary scores.
Shares and the Gini coefficient are scored in percentage points.

**Summary scores.** Mean absolute error within a wave pair over:

- *level*: mean, p25, p50, p75, p90, p99 (percent);
- *distribution*: top 10% share, top 1% share, Gini coefficient (percentage
  points);
- *subgroup*: the ten group medians (percent).

**Sampling noise.** Standard errors follow the codebook: variance across the
999 replicate weights on the first implicate, plus 6/5 of the variance across
implicates. The projection is redone under each replicate's weights for (d),
whose groups depend on the weights. An error is called within noise when it is
smaller than 1.96 standard errors of the difference between the projected and
actual statistic, treating the two waves as independent samples and the
aggregate factors as known.

## What counts as winning and failing

1. For each summary score, the winner is the contender with the lowest mean
   over the twelve wave pairs. The number of pairs each contender wins is
   reported next to it. Because (d) is in-sample on eleven pairs, it is left
   out of the twelve-pair call and judged with its real-time variant against
   (a), (b) and (c) on 2016→2019, 2019→2022 and 2022→2025.
2. The 2022→2025 pair is reported on its own, with the same three scores.
3. Aging beats doing nothing where (b), (c) or (d) has a lower level score
   than (a).
4. A method fails on a statistic in a wave pair when its error is outside
   noise. Every method fails where all four do.

The headline chart shows, for 2022→2025, each contender's percent error at
p10 (in percent of the median), p25, p50, p75, p90, p99 and the mean, against
a band of 1.96 standard errors.

The actual 2022 and 2025 values are checked against the Fed's report (Table 2,
2025 dollars: median $211.1k and $215.9k, mean $1,164.1k and $1,241.5k). The
public file drops respondents wealthy enough for the Forbes list and rounds
and blurs values (2022 codebook, "Disclosure review"), so a small gap is
expected. In the 2022 public file the mean is $1,159.4k and the median
$210.9k stacked or $210.2k averaged over implicates.

## Invariants

Tested with Hypothesis in `tests/`:

- Uniform scaling leaves the Gini coefficient and top shares unchanged and
  multiplies the mean and every quantile by the factor.
- Class scaling multiplies each class's weighted total by exactly its factor.
- Projections are deterministic and do not depend on row order.
- Weights, household identifiers and demographics come out bit-for-bit
  identical, and the input is not modified.
- Net worth equals assets minus debt after every projection.
- Unit factors, and no change, return the input exactly; equal factors across
  classes or groups reduce to uniform scaling; identical class factors in
  every group reduce to class scaling.
- Wealth groups partition households in rank order, and each group's weight
  share is within one household of its target.
- Factors chain: the factor from *t* to *t+6* is the product of the two
  three-year factors, and a wave projected onto itself is unchanged.

Differential checks: the quantile against NumPy's weighted inverse-CDF
quantile and against repeated observations; the Gini coefficient against the
mean-difference formula; top shares against direct accumulation from the top;
the DFA group totals against the FRED household net worth series; the
committed results against a fresh run; the actual waves against the Fed's
published figures.

## What was known when this was frozen

- The Fed's published all-family mean and median net worth for 2022 and 2025,
  quoted above.
- The aggregate inputs, including their 2025 values. They are inputs to the
  projection, so they were downloaded and checked. Two 2025:Q3 levels (total
  financial assets and the equity share of them) were read while checking the
  Z.1 accounting identity. The 2022→2025 factors were not computed.
- Every method's scores on the eleven pairs through 2019→2022, committed
  under `results/` at this tag. The methods have no fitted parameters. The
  quarter, the deflator and the series for each class were fixed before any
  pair was scored and have not changed since.
- One method was respecified on the development pairs. (d) first used a
  single factor per group, from the group's DFA net worth. The bottom half's
  net worth is a small difference between its assets and its debts, and that
  factor ran from 0.24 (2007→2010) to 1.81 (2010→2013). (d) now scales assets
  and debt by separate factors. The first version stays as
  `d_dfa_groups_net_worth`.
- Not known: anything from the 2025 microdata, or any 2025 projection.

## Deviations

None at `prereg-v1`.
