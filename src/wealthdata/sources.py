"""Download and snapshot the aggregate series the backtest uses.

Everything here is input data for the projections: Financial Accounts (Z.1)
household balance sheet series, the household count, the CPI-U-RS values the
Federal Reserve uses to deflate the SCF, and Distributional Financial Accounts
(DFA) net worth by wealth group. Running ``python -m wealthdata.sources``
rewrites ``data/aggregates/`` and its ``MANIFEST.json``. The committed
snapshot, not a fresh download, is what the backtest reads, so results do not
move when the Fed revises a series.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

#: federalreserve.gov returns 403 to the default urllib agent; FRED times out
#: on browser agents. Both accept a descriptive one.
USER_AGENT = "wealthdata/0.1 (+https://github.com/MaxGhenis/wealthdata)"

AGGREGATES_DIR = Path(__file__).resolve().parents[2] / "data" / "aggregates"

#: Z.1 release whose CSV bundle is snapshotted (2026:Q2 release).
Z1_RELEASE = "20260911"
Z1_ZIP_URL = f"https://www.federalreserve.gov/releases/z1/{Z1_RELEASE}/z1_csv_files.zip"

#: Tables in the Z.1 bundle that carry the series below.
Z1_TABLES = ("S1M_b", "S1M_e_b")

#: Quarterly level series (millions of dollars, not seasonally adjusted).
Z1_SERIES = (
    "FL152090005",  # households and nonprofits; net worth
    "FL152000005",  # total assets
    "FL154090005",  # total financial assets
    "LM153064475",  # directly and indirectly held corporate equities
    "FL154000005",  # total currency and deposits
    "FL153034005",  # money market fund shares
    "LM154022375",  # directly and indirectly held debt securities
    "FL154035005",  # loans (asset)
    "FL153099475",  # other financial assets
    "LM155035015",  # households; owner-occupied real estate at market value
    "LM153081115",  # other equity (tracks proprietors' equity in noncorporate business)
    "LM155111005",  # consumer durable goods
    "FL154190005",  # total liabilities
)

BULLETIN_MACRO_URL = "https://www.federalreserve.gov/econres/files/bulletin.macro.txt"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
ALFRED_CSV = (
    "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={vintage}"
)

#: Households; net worth (the series the 2019 README names) and the CPS count
#: of households.
FRED_SERIES = ("BOGZ1FL192090005Q", "TTLHH")

#: Vintages of the README series as it stood on 30 June of the year after
#: each target wave, before that wave's SCF was published.
REAL_TIME_NET_WORTH_VINTAGES = ("2020-06-30", "2023-06-30", "2026-06-30")

DFA_URL = "https://www.federalreserve.gov/releases/z1/dataviz/download/dfa-networth-levels.csv"
#: Internet Archive capture of the same file from before the 2022 SCF was
#: published (18 October 2023).
DFA_WAYBACK_URL = "http://web.archive.org/web/20230922214757id_/" + DFA_URL
#: FRED carries the DFA net worth levels by wealth group; ALFRED keeps vintages.
#: The 2020 vintage predates the split of the top 1% at the 99.9th percentile,
#: so it has four groups.
DFA_FRED_SERIES = {
    "Top1": "WFRBLT01026",
    "Next9": "WFRBLN09053",
    "Next40": "WFRBLN40080",
    "Bottom50": "WFRBLB50107",
}
#: ALFRED vintage from before the 2019 SCF was published (28 September 2020).
DFA_ALFRED_VINTAGE = "2020-06-30"


def fetch(url: str, *, retries: int = 5) -> tuple[bytes, str | None]:
    """Return the body and Last-Modified header of ``url``."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read(), response.headers.get("Last-Modified")
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(5 * 2**attempt)
    raise AssertionError("unreachable")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_cpi_u_rs(macro: str) -> dict[int, int]:
    """Read September CPI-U-RS (times ten) by survey year from the Fed's macro.

    The macro that builds the summary extract sets ``CPIADJ=&CPIBASE/<value>``
    inside one ``%IF (&YEAR=<year>)`` block per survey year, where ``<value>``
    is the September CPI-U-RS of that year without its decimal point.
    """
    pattern = re.compile(r"%IF \(&YEAR=(\d{4})\) %THEN %DO;\s*%LET CPIADJ=&CPIBASE/(\d+);")
    values = {int(year): int(cpi) for year, cpi in pattern.findall(macro)}
    if not values:
        raise ValueError("no CPIADJ blocks found in the bulletin macro")
    return values


def parse_z1(zip_bytes: bytes) -> tuple[list[tuple[str, str, int]], dict[str, str]]:
    """Extract the series in :data:`Z1_SERIES` from the Z.1 CSV bundle.

    Returns tidy ``(date, series, value)`` rows and each series' description
    from the bundle's data dictionary.
    """
    rows: dict[tuple[str, str], int] = {}
    descriptions: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for table in Z1_TABLES:
            dictionary = archive.read(f"data_dictionary/{table}.txt").decode("latin-1")
            for line in dictionary.splitlines():
                fields = line.split("\t")
                code = fields[0].removesuffix(".Q")
                if code in Z1_SERIES:
                    descriptions[code] = fields[1].strip()
            table_text = archive.read(f"csv/{table}.csv").decode("latin-1")
            reader = csv.reader(io.StringIO(table_text))
            header = [name.removesuffix(".Q") for name in next(reader)]
            for record in reader:
                for name, value in zip(header[1:], record[1:], strict=True):
                    if name not in Z1_SERIES or value in ("ND", ""):
                        continue
                    key = (record[0].replace(":", "-"), name)
                    number = int(value)
                    if rows.setdefault(key, number) != number:
                        raise ValueError(f"{name} differs between Z.1 tables at {record[0]}")
    missing = set(Z1_SERIES) - set(descriptions)
    if missing:
        raise ValueError(f"series missing from the Z.1 bundle: {sorted(missing)}")
    tidy = [(date, series, value) for (date, series), value in sorted(rows.items())]
    return tidy, descriptions


def _write_csv(path: Path, header: list[str], rows: list) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    data = buffer.getvalue().encode()
    path.write_bytes(data)
    return data


def _fred_rows(body: bytes) -> list[tuple[str, str]]:
    reader = csv.reader(io.StringIO(body.decode()))
    header = next(reader)
    if header[0] != "observation_date":
        raise ValueError(f"unexpected FRED response header: {header}")
    return [(date, value) for date, value in reader if value not in ("", ".")]


def build(out_dir: Path = AGGREGATES_DIR) -> dict:
    """Download every aggregate input and write the snapshot plus manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}

    def record(name: str, data: bytes, url: str, last_modified: str | None, **extra) -> None:
        manifest[name] = {
            "url": url,
            "retrieved_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_last_modified": last_modified,
            "sha256": sha256(data),
            **extra,
        }

    macro, modified = fetch(BULLETIN_MACRO_URL)
    cpi = parse_cpi_u_rs(macro.decode("latin-1"))
    data = _write_csv(
        out_dir / "cpi_u_rs_september.csv",
        ["year", "cpi_u_rs_september_x10"],
        sorted(cpi.items()),
    )
    record(
        "cpi_u_rs_september.csv",
        data,
        BULLETIN_MACRO_URL,
        modified,
        source_sha256=sha256(macro),
    )

    bundle, modified = fetch(Z1_ZIP_URL)
    tidy, descriptions = parse_z1(bundle)
    data = _write_csv(out_dir / "z1_household_balance_sheet.csv", ["date", "series", "value"], tidy)
    record(
        "z1_household_balance_sheet.csv",
        data,
        Z1_ZIP_URL,
        modified,
        source_sha256=sha256(bundle),
        units="millions of dollars, end of quarter, not seasonally adjusted",
        series=descriptions,
    )

    for series in FRED_SERIES:
        url = FRED_CSV.format(series=series)
        body, modified = fetch(url)
        name = f"fred_{series}.csv"
        data = _write_csv(out_dir / name, ["date", "value"], _fred_rows(body))
        record(name, data, url, modified)

    rows = []
    for vintage in REAL_TIME_NET_WORTH_VINTAGES:
        url = ALFRED_CSV.format(series=FRED_SERIES[0], vintage=vintage)
        body, _ = fetch(url)
        rows += [(vintage, date, value) for date, value in _fred_rows(body)]
    name = f"alfred_{FRED_SERIES[0]}.csv"
    data = _write_csv(out_dir / name, ["vintage", "date", "value"], rows)
    record(name, data, ALFRED_CSV.format(series=FRED_SERIES[0], vintage="{vintage}"), None)

    body, modified = fetch(DFA_URL)
    (out_dir / "dfa_networth_levels_current.csv").write_bytes(body)
    record("dfa_networth_levels_current.csv", body, DFA_URL, modified)

    body, modified = fetch(DFA_WAYBACK_URL)
    (out_dir / "dfa_networth_levels_wayback_20230922.csv").write_bytes(body)
    record("dfa_networth_levels_wayback_20230922.csv", body, DFA_WAYBACK_URL, modified)

    rows = []
    for category, series in DFA_FRED_SERIES.items():
        url = ALFRED_CSV.format(series=series, vintage=DFA_ALFRED_VINTAGE)
        body, _ = fetch(url)
        rows += [(date, category, value) for date, value in _fred_rows(body)]
    name = "dfa_networth_alfred_20200630.csv"
    data = _write_csv(out_dir / name, ["date", "category", "net_worth"], sorted(rows))
    record(
        name,
        data,
        ALFRED_CSV.format(series="{series}", vintage=DFA_ALFRED_VINTAGE),
        None,
        series=DFA_FRED_SERIES,
    )

    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    for name, entry in build().items():
        print(f"{name}  {entry['sha256'][:12]}  {entry['source_last_modified']}")
