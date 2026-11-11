# Where each mechanism claim comes from

Every statement in this repository about how the SCF, the Financial Accounts
or the DFA are built was read from the sources below on 9 October 2026. Quotes
are verbatim.

## SCF summary extract

**Deflator.** `https://www.federalreserve.gov/econres/files/bulletin.macro.txt`
(SHA-256 in `data/aggregates/MANIFEST.json`):

> for all other values, set CPICUR equal to CPIBASE divided by the value of
> CPI-U-RS * 100 for the September of the survey year

The macro sets `CPIADJ=&CPIBASE/<September value>` once per survey year and is
run with `CPIBASE=4789` (September 2025) for the real-dollar files.
`wealthdata.sources.parse_cpi_u_rs` reads those values.

**Weights.** Same macro: `WGT=X42001/5`, "divide weight by 5 so totals
estimated on the 5 implicates jointly are correct". Adjustments that dampen
influential cases apply only when `PUBLIC NE YES`, that is, to the internal
file.

**Variables.** Same macro: `FIN=LIQ+CDS+NMMF+STOCKS+BOND+RETQLIQ+SAVBND+CASHLI+OTHMA+OTHFIN`,
`NFIN=VEHIC+HOUSES+ORESRE+NNRESRE+BUS+OTHNFIN`, `ASSET=FIN+NFIN`. `EQUITY`
sums directly held stock, stock mutual funds, and the stock-invested parts of
retirement accounts, annuities, trusts and (from 2007) savings accounts such
as 529 plans. Those savings balances are also in `LIQ`: from 2004 the macro
adds `X3730` and its five siblings to `SAVING`, `MMDA` or `MMMF` by account
type (all part of `LIQ`), and
from 2007 adds the stock-invested part of the same items to `EQUITY` and
`SAVEQ`.

**Implicates and standard errors.** 2022 codebook,
`https://www.federalreserve.gov/econres/files/codebk2022.txt`:

> For users who want to estimate only simple statistics such as sums, means
> and medians ignoring the effects of imputation error on the standard errors
> of these estimates, it will probably be sufficient to divide the weights by
> 5.

> An estimate of the total standard error attributable to imputation and
> sampling is given by SQRT((6/5)*imputation variance + sampling variance).

> Replicate weights were computed only for the first implicate of each case.
> For many purposes, users of the replicate weight files will probably want
> to multiply the weight times the multiplicity

The codebook's `MEANIT` program reports the mean over implicates of each
implicate's mean and median and computes sampling variance from the 999
replicates on implicate 1. Its median is the first value whose cumulative
weight share is at least one half:

    IMP[,2]=CUSUM(IMP[,2])/POP;
    ID[1,I]=IMP[MIN(LOC(IMP[,2]>=.5)),1];

`wealthdata.stats.weighted_quantile` uses the same rule for every quantile.

On replicate weights the codebook says "in all cases the sum of each of the
weights times the corresponding multiplicities of the cases equals the total
number of households", and its program notes that "where cases not selected
for a replicate, there are missing values in these variables" before taking
`MAX(0,MULT{I})*MAX(0,RWGT{I})`. `wealthdata.replicates` does the same.

**Public versus internal file.** Same codebook, "Disclosure review":

> Continuous variables were rounded. Data were also blurred by other means
> intentionally not specified.

> the public version of the data set contains 4,595 of the 4,602 observations
> in the full data set

The seven dropped observations are those with "net worth at least equal to
the minimum level needed to qualify for the Forbes list". The 2025 codebook
(`codebk2025.txt`, read after the freeze) gives "4,360 of the 4,367
observations" and has the same `MEANIT` median rule.

## Financial Accounts (Z.1)

Series names and tables are from the data dictionaries inside
`https://www.federalreserve.gov/releases/z1/20260911/z1_csv_files.zip`,
tables S1M.b ("Households and nonprofit organizations") and S1M.e.b ("Balance
sheet of households and nonprofit organizations with debt and equity holdings
detail"). The descriptions are copied into `MANIFEST.json`.

In S1M.e.b, total financial assets equal currency and deposits, money market
fund shares, directly and indirectly held debt securities, loans, directly
and indirectly held corporate equities, and other financial assets
(`tests/test_aggregates.py` checks this for every quarter). The indirect
holdings listed there are through life insurance companies, private defined
contribution pension funds, the federal Thrift Savings Plan, state and local
government employee pension funds, and mutual funds.

`LM153081115`, "other equity", tracks FRED `BOGZ1LM152090205Q`, proprietors'
equity in noncorporate business. In a one-time comparison on 9 October 2026
(FRED series not in the snapshot) the two were equal in 291 of the 305
quarters they share and differed by at most $7.9 billion (0.12%) in the other
14, from 2009:Q4 to 2013:Q1. The study uses `LM153081115` because it is the
series in the published table.

`BOGZ1FL192090005Q`, "Households; Net Worth, Level", is quarterly on FRED from
1987:Q4. The Z.1 bundle carries the households-only sector annually (table
S14.b), so the quarterly series comes from FRED.

## Distributional Financial Accounts

`https://www.federalreserve.gov/releases/z1/dataviz/dfa/index.html`:

> The second step is to transform the reconciled SCF balance sheet (which is
> measured every three years) into an up-to-date, quarterly balance sheet by
> interpolating the assets and liabilities for each sub-population on a
> quarterly basis between SCF surveys, and forecasting these balance sheets
> for each quarter beyond the most recent survey year.

The DFA download carried `Last-Modified: Fri, 18 Sep 2026`, three weeks before
the 2025 SCF, and is byte-identical to the Internet Archive's capture of 7
October 2026 (`MANIFEST.json`, checked in `tests/test_aggregates.py`). The
five wealth groups in that file sum to `BOGZ1FL192090005Q` within 0.04% in
every quarter.

In every vintage used, each group's assets less liabilities equal its net
worth to within rounding (`tests/test_aggregates.py`).

Earlier vintages: the Internet Archive capture of 22 September 2023 predates
the 2022 SCF (published 18 October 2023). On ALFRED, the top 1% series
`WFRBLT01026` is unchanged from the 30 June 2020 vintage through 30 September
2020 and its 2019:Q3 value is revised by the 31 October 2020 vintage, after the 2019 SCF
was published on 28 September 2020. Only that series was checked this way;
the other groups and the asset and liability series in the same vintage are
assumed to follow the same release schedule.

## Household count

FRED `TTLHH`, "Total Households", annual, from the Census Bureau's Current
Population Survey Annual Social and Economic Supplement.
