# Independent review of the design before the freeze

Run on 10 October 2026 by an Opus 5.5 agent on a Subfleet lane (job `20261009-210849-wealthdata-prereg-review`), reading the working tree at commit `f626eba`. It could not run code. Its finding B1 describes a mutation left in `stats.py` by an interrupted mutation-testing run, not the committed code; see "What was known" in `PREREGISTRATION.md`. The review follows unedited.

---

# Review: SCF wealth-aging backtest pre-registration (before the 2025 data are opened)

**Verdict: FREEZE AFTER FIXES.** Four fixes are needed:
1. Correct the quantile tie rule in `stats.py`.
2. Make the decision rules something two people would apply the same way.
3. State which 2025 statistics are already known, and add a blind sub-score.
4. Correct the claim that the 2022→2025 factors were never computed.

None of these needs the 2025 microdata.

**I could not run anything.** This session had no shell, so `pytest`, the Python snippets and every counterexample below are traced by hand from the code. Before relying on any of them, run the commands given with each finding.

---

## Blocking findings

### B1. The quantile rule is coded as "strictly greater than", not "reaches", so the repository's own tests should fail
`src/wealthdata/stats.py:58`:
```python
index = min(int(np.searchsorted(cumulative, target, side="right")), x.size - 1)
```
`side="right"` returns the first index where the cumulative weight is strictly greater than the target. The pre-registration (`PREREGISTRATION.md:146-148`), the docstring at `stats.py:47` and `docs/sources.md:46` all say "at least". NumPy's `inverted_cdf`, which the tests compare against, also uses "at least".

Hand traces of tests in `tests/test_stats.py`:
- **`test_known_values` (`:160-161`).** Values `[1,2,3]`, weights `[1,1,2]`, q = 0.5. The cumulative weights are `[1,2,4]` and the target is 2.0. `searchsorted(side="right")` returns 2, so the function gives 3.0; the test asserts 2.0.
- **`test_quantile_with_integer_weights_equals_repeated_observations` (`:46-55`).** Hypothesis will find `[(0,1),(1,1)]` at q = 0.5: the function returns 1, NumPy returns 0.

`git status` shows `src/wealthdata/stats.py` modified but not staged. So the committed `results/` may come from a different version of this function than the one in the working tree.

On real SCF weights (floats from `X42001/5`), a cumulative sum landing exactly on the target is rare. The numbers in `results/` are probably unaffected, but the stated definition, the code and the tests disagree.

- **Fix:** use `side="left"`, or compare `cumulative / cumulative[-1] >= q` so the normalisation matches NumPy exactly.
- **Then run:** `uv run pytest -q tests/test_stats.py` and `uv run pytest -q -m scf tests/test_backtest.py::test_committed_results_match_a_fresh_run`.

### B2. The decision rules are mostly settled by the development pairs already, and the confirmatory part has no rule
`PREREGISTRATION.md:179-188`:

- **The twelve-pair call is 11/12 known.** Summing level scores over the eleven development pairs in `results/summary.csv`:
  - (a) 156.94
  - (b) 129.65
  - (c) 121.79

  (b) takes the twelve-pair level call from (c) only if (c)'s 2022→2025 level score exceeds (b)'s by more than **7.86 points**. (a) would need to beat (c) by about 35 points. So Rule 1's level winner is close to decided before 2025 is opened. The same holds for Rule 3 ("aging beats doing nothing where … lower level score than (a)") if read over all twelve pairs: (b)'s eleven-pair mean is already 11.8 against (a)'s 14.3.
- **Rule 2 names no winner.** It says only that 2022→2025 "is reported on its own". Yet `report/report.qmd:92-96` declares a 2022→2025 winner with `report.winner(R, "level", ALL, (TARGET,))`. The only out-of-sample result therefore gets an informal winner that the design does not define.
- **Rule 3 has no scope.** "Where" could mean per pair, on the twelve-pair mean, or on 2022→2025 only. It also compares the best of three methods against (a), which favours "aging wins" by chance.
- **Rule 4 does not parse.** "Every method fails where all four do" has no clear meaning. The set of statistics is also unstated: `report.qmd:160` passes `all_fail` the mean, p10–p99 and the distribution statistics, but not the subgroup medians.
- **Rule 1 says (d) is left out of the twelve-pair call, but its wins are counted.** `report.score_table(R, report.CONTENDERS)` (`report.qmd:106`, `report.py:135`) includes in-sample (d) when counting "pairs won", which lowers the counts for (a), (b) and (c).
- **Ties and rounding are unspecified.** `report.winner` (`report.py:415`) breaks ties by tuple order, which favours (a). Tables round to one decimal place.

**Fix:** state that 2022→2025, plus the three-pair real-time comparison, is the confirmatory test. Name its winner rule per score. Say what result would contradict the development ranking. Then:
- define Rule 3 per pair and on 2022→2025;
- rewrite Rule 4 as "report each (pair, statistic) where all four contenders are outside noise, over statistics X";
- count pairs won only among (a), (b) and (c) for the twelve-pair table;
- set a tie rule using unrounded values.

### B3. The 2025 mean and median are already known, so two of the six level statistics are not blind
`PREREGISTRATION.md:194-196` and `report.qmd:33` quote the Fed's 2025 values: median $215.9k and mean $1,241.5k. Together with the 2022 public-file values at `:198-199`, the 2025 no-change errors follow directly:
- mean: about 1159.4 / 1241.5 − 1 ≈ **−6.6%**
- median: about 210.2 / 215.9 − 1 ≈ **−2.6%**

(These are against the internal-file figures; the public-file gap is about 0.4%.)

Anyone who computes the uniform factor, or who read the two 2025:Q3 Z.1 levels mentioned at `:232-234`, also knows (b)'s and (c)'s mean errors to within the public/internal gap. This is disclosed, but the document still calls 2025 "the one target not used while building the methods" (`:13-14`) and does not draw the consequence.

**Fix:**
- Add a pre-specified *blind level* sub-score for 2022→2025 over p25, p75, p90 and p99.
- State in "What was known" that (a)'s 2025 mean and median errors follow from published figures.

### B4. "The 2022→2025 factors were not computed" (`PREREGISTRATION.md:234`) is false: the test suite computes them
- `tests/test_aggregates.py:72-79` loops `scf.WAVES[:-1]`, which includes 2022. It calls `net_worth_factor(2022, 2025)` with and without the household adjustment, and asserts bounds on the household and price ratios.
- `tests/test_aggregates.py:118-126` calls `dfa_group_factors(2022, 2025, vintage="current", measure=m)` for all three measures and asserts each is positive.
- `tests/test_aggregates.py:47-61` uses every seventh wave triple. Some of these end in 2025, so `class_factors(…, 2025)` is evaluated.

Nothing is printed unless an assertion fails, so "not inspected" may be true; "not computed" is not.

**Fix:** reword to "computed by the test suite but never displayed", or leave 2025 out of those tests until the freeze.

---

## Non-blocking findings

1. **Concept mismatches missing from "known mismatches" (`PREREGISTRATION.md:85-90`).**
   - (b) and (d) use Z.1/DFA household net worth, which includes defined-benefit pension entitlements and all consumer durables. SCF net worth excludes both.
   - (c) equities: `docs/sources.md:73-75` itself lists state and local *defined-benefit* pension funds among the indirect holdings in `LM153064475`.
   - Housing: `oresre` includes rented 1–4 family properties, which Z.1 puts in noncorporate business. Z.1 owner-occupied real estate covers "second homes that are not rented" (B.101.h, see source 1).
   - Other financial: this class holds cash-value life insurance and the non-equity parts of retirement accounts, but is scaled by debt securities.
   - Other nonfinancial: the SCF holds vehicles at market value; Z.1 consumer durables are at current cost. Used-car prices rose sharply in 2021–22.
   - Debt: `FL154190005` includes nonprofit liabilities.

   Disclose these; no change to the mapping is needed.

2. **Noise criterion (`PREREGISTRATION.md:169-175`, `backtest.py:361-382`).**
   - About 19 statistics × 12 pairs × 4 methods are tested at 1.96 SE, so roughly 5% of cells will "fail" even if every true error were zero. Report the expected number of false fails.
   - "Within noise" is a failure to reject, not evidence of accuracy. The top-1% share and the subgroup medians have wide SEs and will pass easily.
   - For in-sample (d), the DFA factors are partly built from the target SCF. The projection is then correlated with the actual value, so the independence assumption overstates the SE and the test goes easy on (d).
   - The criterion ignores uncertainty in the factors (Z.1 revisions, DFA's own reliance on the SCF). This is stated, which is fine.

3. **Missing replicate weights become zero silently.** `replicates.py:94` applies `np.nan_to_num(np.maximum(...))`. A NaN weight or multiplicity drops the household from that replicate without warning. The `reindex` check at `:127` cannot catch this, because the NaN has already been replaced. Fail loudly instead.

4. **Results depend on row order when net worth ties at a group boundary.** `project.py:106` breaks ties by input order. Hand counterexample: two households, each with weight 1 and net worth 0. Household A has assets 10 and debt 10; household B has neither. Bottom50 receives whichever row comes first, so swapping the rows changes A's projected net worth when the Bottom50 and Next40 factors differ. `test_project.py:95` skips this case with `assume(no duplicated networth)`, so the invariant "do not depend on row order" (`PREREGISTRATION.md:208`) is only tested where it trivially holds. The effect on SCF data is likely nil, since ties at p50, p90 and above are unlikely. Fix: break ties by `case`, or qualify the claim.

5. **Some tests are weaker than the claims they back.**
   - `test_aggregates.py:155` only asserts a string stored in the manifest, so it is no evidence that the DFA file predates the 2025 release.
   - `test_aggregates.py:110` allows a 0.1% gap where `docs/sources.md:98-99` claims 0.04%.
   - `test_project.py:82` (`assert_array_equal(projected[name], sheet[name]*factor)`) restates the implementation. This is acceptable as an invariant, but the real-data check at `test_backtest.py:136` is the meaningful one.

6. **Claims that go beyond their evidence.**
   - `sources.md:45-48`: the description of how `MEANIT` picks the median is a paraphrase with no quote, and B1 shows the code disagrees with it.
   - `sources.md:25-28`: the claim that 529-type savings accounts sit in both `EQUITY` and `LIQ` is unquoted. Nothing in the repo counts the households with negative "other financial".
   - `sources.md:77-81`: the 291/305-quarter comparison against `BOGZ1LM152090205Q` cannot be reproduced from the repo, because that series is not in the snapshot.
   - `sources.md:105-108`: the ALFRED revision check covers only `WFRBLT01026` (top 1% net worth), not the assets and liabilities series or the other groups that `d_dfa_groups_real_time` uses.
   - `test_scf.py:87`: the comment attributes "replicate weights sum to households" to the codebook without a quote.

7. **No rule if a 2025 subgroup median or p25 is ≤ 0.** `summarize` raises at `backtest.py:300-301`. That is unlikely, but the design does not say what happens.

8. **Household counts.** CPS ASEC population-control updates (for example the January 2025 immigration revision) put steps into `TTLHH`, and SCF families are not the same unit as CPS households. Suggestion: report (b) with H taken from the base wave's weight total to show how sensitive the result is.

9. **The `houses = -1` code** (`test_scf.py:39`) is scaled as if it were a dollar amount. The effect is negligible.

10. **The "current" DFA vintage rests on one HTTP `Last-Modified` header.** The file was retrieved on 2026-10-10 01:14 UTC, after the 2025 release. Suggestion: check against a Wayback capture taken between 18 September and 9 October 2026.

---

## Checked and found sound
- **Factor formula and real/nominal handling.** Real ratio = nominal ratio ÷ CPI ratio, consistent with how the extract is deflated (`CPIADJ = CPIBASE / Sept CPI`). Dividing by household growth is correct for per-household statistics with fixed weights (`aggregates.py:142-149`).
- **Quarter dating.** FRED's Q3 is dated `YYYY-07-01` and `_quarter_label` maps it to Q3; Z.1 dates `2022:Q3` become `2022-Q3`; all levels are end of period.
- **The seven classes partition net worth exactly.** They sum to `fin + nfin − debt`, and `test_scf.py:32-36` checks this against the extract within $1.
- **The DFA real-time vintages are leak-free.** June 2020 is before the 2019 SCF (28 Sep 2020), September 2023 before the 2022 SCF (18 Oct 2023), and 18 Sep 2026 before the 2025 SCF. In each, the base quarter is benchmarked to the base SCF and the target quarter is a DFA forecast. The in-sample label for current-vintage (d) through 2022 is correct.
- **`TTLHH` is not a leak.** It was published 4 Dec 2025, before the 2025 SCF.
- **Using current-vintage Z.1 for historical pairs is disclosed** (`PREREGISTRATION.md:42-44`).
- **(d) is well defined.** Separate asset and debt factors avoid the near-zero Bottom50 net-worth base; negative factors raise an error (`project.py:72`); the midpoint rule gives each household exactly one group.
- **Implicates.** The mean of per-implicate statistics matches the codebook; the stacked version is a stated check.
- **Top shares and Gini with negative net worth.** Both are well defined for a positive total; the Gini can exceed 1, which is acceptable.
- **p10** is scored as a percentage of the median and excluded from the summary scores (`backtest.py:23, 227-229`).
- **Standard errors** follow the quoted formula: implicate variance × 6/5 plus replicate variance on implicate 1. Replicate weights are paired with multiplicities by index `i`, and the projection is redone per replicate for (d).
- **The int16 id overflow** is handled by widening before multiplying (`scf.py:147-148`). 1989's `x1`/`xx1` columns are renamed, and every household is checked for five implicates.
- **The merges** use `validate="one_to_one"` and `validate="many_to_one"` (`backtest.py:373-378`).
- **`%.10g` output** keeps errors at full precision, because the difference is computed before writing.
- **Weights are asserted unchanged** on every projection (`backtest.py:275`).

## What I could not check
- **Running `pytest`, `backtest.run(2022)` and the counterexamples**: this session had no shell. Everything above is traced by hand.
- **The `MEANIT` source text**: needed to settle whether the codebook uses "at least" or "strictly greater" in its quantile rule.
- **Whether Z.1 household series are benchmarked to the SCF.** If they are, (b) and (c) would also be partly in-sample for historical pairs. A search did not settle this; it needs the Financial Accounts Guide series notes.
- **The contents of the 1989 extract and replicate files**, the TTLHH values, and the 2025 factors: none were opened, per the hard rules.

Sources:
- [Z.1 B.101.h, households balance sheet](https://www.federalreserve.gov/releases/z1/20250313/html/b101h.htm)
- [Z.1 S.14.b](https://www.federalreserve.gov/releases/z1/current/html/S14_b.htm)