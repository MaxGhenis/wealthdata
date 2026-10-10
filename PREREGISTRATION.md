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
2026, is the one target whose microdata were not used while building the
methods. Its all-family mean and median were already public (see
[What was known](#what-was-known-when-this-was-frozen)).

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
except owner-occupied real estate, which is households only.

Known mismatches, accepted as part of the method and not changed after
review:

- *Business.* SCF business equity covers privately held businesses of every
  legal form, including S and other corporations (2022 codebook, `X3119`); the
  series covers noncorporate business only.
- *Equities.* The series counts equities held indirectly through life insurers
  and state and local government employee pension funds (table S1M.e.b),
  which the SCF does not count as household equity.
- *Housing.* `oresre` includes every 1-4 family property other than the main
  home, rented or not (bulletin macro); the series is owner-occupied real
  estate.
- *Other financial.* This class holds bonds, cash-value life insurance, other
  managed assets and the non-stock part of retirement accounts; the series is
  debt securities only.
- *Other nonfinancial.* SCF vehicles and a listed set of valuables against all
  consumer durable goods at current cost.
- *Debt.* The series includes nonprofit organizations' liabilities.
- *Overlap.* Since 2007 `equity` includes savings accounts invested in stocks,
  and the same balances are in `liq` (macro: `X3730` and its siblings enter
  both `LIQ` and `EQUITY`). "Other financial" is negative for
  0.35% to 1.0% of families in 2007-2022 and for none before.
- *Net worth concept.* Methods (b) and (d) grow SCF net worth at the rate of a
  broader aggregate that also includes defined benefit pension entitlements
  and all consumer durables (both are columns of the DFA file, which sums to
  household net worth). SCF net worth counts pensions only where they sit in
  an account (macro: "future pensions (accumulated in an account").

Whether any Financial Accounts household series is itself benchmarked to the
SCF was not checked. If one is, (b) and (c) are partly in-sample on the
historical pairs, as (d) is.

**(d) DFA wealth groups.** Households are ranked by net worth within each
implicate and placed in the DFA's groups (bottom 50%, 50th to 90th, 90th to
99th, 99th to 99.9th, top 0.1%) by the midpoint of the weight interval they
occupy, with ties broken by household id. Every asset class is multiplied by the factor for the group's DFA
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
Any other dollar statistic whose actual value is zero or negative is scored
the same way. Shares and the Gini coefficient are scored in percentage
points.

**Summary scores.** Mean absolute error within a wave pair over:

- *level*: mean, p25, p50, p75, p90, p99 (percent);
- *blind level*: p25, p75, p90, p99 (percent), the level statistics whose
  2025 values had not been published;
- *distribution*: top 10% share, top 1% share, Gini coefficient (percentage
  points);
- *subgroup*: the ten group medians (percent).

**Sampling noise.** Standard errors follow the codebook: variance across the
999 replicate weights on the first implicate, plus 6/5 of the variance across
implicates. The projection is redone under each replicate's weights for (d),
whose groups depend on the weights. An error is called within noise when it is
smaller than 1.96 standard errors of the difference between the projected and
actual statistic, treating the two waves as independent samples and the
aggregate factors as known. This is a test that can fail to reject, not a
measure of accuracy: at 1.96 standard errors about one cell in twenty is
outside noise when the true error is zero, and statistics with wide standard
errors (the top 1% share, the subgroup medians) pass easily. For in-sample
(d) the projection is correlated with the target, so the independence
assumption overstates the standard error.

## What counts as winning and failing

Scores are compared unrounded. Exactly equal scores are reported as a tie.

1. **The confirmatory test is 2022→2025.** For each of the four summary
   scores, the winner is the contender, among (a) to (d), with the lowest
   score on that pair. The current DFA vintage predates the 2025 SCF, so (d)
   is a forecast here. The blind level score is the cleanest of the four
   (see [What was known](#what-was-known-when-this-was-frozen)).
2. **The development ranking.** On the eleven development pairs, asset-class
   scaling has the lowest mean level score of (a), (b) and (c). That ranking
   is contradicted if, on 2022→2025, (a) or (b) has a lower level score or a
   lower blind level score than (c).
3. **The twelve-pair record** is the mean of each score over all twelve pairs
   for (a), (b) and (c), with the number of pairs each wins among those
   three. (d) is in-sample on eleven pairs, so it is left out of this record
   and judged instead with `d_dfa_groups_real_time` against (a), (b) and (c)
   on the three pairs with a real-time vintage: 2016→2019, 2019→2022 and
   2022→2025.
4. **Aging against doing nothing.** For each of (b) and (c), the number of
   the twelve pairs on which its level score is below (a)'s, and whether it
   is below on 2022→2025. For (d), the same on the three real-time pairs.
   Each method is judged on its own, not the best of the three.
5. **Failures.** A method fails on a statistic in a wave pair when its error
   is outside noise. Over the twenty statistics (mean, the six quantiles, the
   two top shares, the Gini coefficient and the ten subgroup medians), the
   report lists every (pair, statistic) where all four contenders fail, and
   for each method the share of cells outside noise against the one in twenty
   expected by chance.

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

Mutation check (`scripts/mutation_check.py`): eighteen deliberate faults,
from nudging the weights to reversing the group ranking to dropping the 6/5
imputation factor, are injected one at a time into a copy of the code; each
must make the tests fail.

Differential checks: the quantile against NumPy's weighted inverse-CDF
quantile and against repeated observations; the Gini coefficient against the
mean-difference formula; top shares against direct accumulation from the top;
the DFA group totals against the FRED household net worth series; the
committed results against a fresh run; the actual waves against the Fed's
published figures.

## What was known when this was frozen

- The Fed's published all-family mean and median net worth for 2022 and 2025,
  quoted above, and nothing else from its report on the 2025 survey. Those two
  figures fix (a)'s 2025 errors on the mean and median to within the gap
  between the public and internal files: about -6.6% on the mean and -2.6%
  on the median. Anyone who also knew the 2022→2025 net worth factor could
  have worked out (b)'s mean error. The blind level score leaves both
  statistics out.
- The aggregate inputs, including their 2025 values. They are inputs to the
  projection, so they were downloaded and checked. Two 2025:Q3 levels (total
  financial assets and the equity share of them) were read while checking the
  Z.1 accounting identity. The test suite computes 2022→2025 factors inside
  assertions (positivity, chaining, household and price ratio bounds); none
  was printed or read.
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
- An independent review of this design, run before the freeze, returned
  "freeze after fixes" (`docs/review-prereg.md`). The fixes are in this
  version: the decision rules above, the blind level score, the disclosures
  in this section and under (c), tie-breaking by household id in (d), and the
  rule for non-positive actual values. Its finding on the quantile rule came
  from a mutation-testing run that had left `side="right"` in
  `weighted_quantile` while the review read the code; the committed code and
  results use `side="left"` (the first value whose cumulative weight share
  reaches the level), as the codebook's `MEANIT` does.
- Not known: anything from the 2025 microdata, or any 2025 projection.

## Deviations

None of the methods, statistics, scores or decision rules changed after
`prereg-v1`. What changed after the tag:

- The 2025 extract and replicate weights were pinned and opened, and the
  backtest was rerun through 2022→2025.
- The tests check the 2025 public extract against the Fed's published 2025
  mean and median, as they already did for 2022.
- Scores are compared at the ten significant digits stored in
  `results/summary.csv`. At that precision (a) and (b) tie on the 2022→2025
  distribution score; they tie exactly in principle, because uniform scaling
  leaves shares and the Gini coefficient unchanged.
- Added to the report after the 2025 results were seen, and labelled as
  such: a summary whose qualitative claims are asserted against the results
  when the report renders, and a table comparing each class's growth in the
  SCF with the Financial Accounts growth applied to it.
- Report presentation: table numbers keep their formatting, and the baseline
  label was removed from the headline chart because it overlapped the data.
