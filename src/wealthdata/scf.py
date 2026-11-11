"""Load the SCF Summary Extract Public Data, one wave at a time.

The Federal Reserve publishes one Stata file per survey year with the summary
variables behind its triennial report. When a new wave comes out the Fed
reissues every earlier year in the new wave's dollars, so all waves read here
are in the same real dollars (2025 dollars in the October 2026 files).

Each household appears five times, once per multiply-imputed *implicate*, and
the extract's weight ``wgt`` is the survey weight divided by five.

A wave can be loaded only after its file's SHA-256 is pinned in
``data/scf_extracts.json``. That makes opening the 2025 file an explicit,
committed step, taken after the methods were frozen.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from wealthdata.sources import fetch

WAVES: tuple[int, ...] = tuple(range(1989, 2026, 3))

EXTRACT_URL = "https://www.federalreserve.gov/econres/files/scfp{year}s.zip"

PINS_PATH = Path(__file__).resolve().parents[2] / "data" / "scf_extracts.json"

#: Balance sheet components (dollars). ``equity`` is the part of financial
#: assets held in stocks, directly or through funds and retirement accounts.
DOLLAR_COLUMNS: tuple[str, ...] = (
    "networth",
    "asset",
    "fin",
    "nfin",
    "debt",
    "equity",
    "liq",
    "cds",
    "houses",
    "oresre",
    "nnresre",
    "bus",
    "vehic",
    "othnfin",
)

#: ``agecl``: age of the reference person, 1 = under 35, 2 = 35-44, 3 = 45-54,
#: 4 = 55-64, 5 = 65-74, 6 = 75 or older. ``racecl4``: 1 = White non-Hispanic,
#: 2 = Black non-Hispanic, 3 = Hispanic, 4 = other or multiple race.
GROUP_COLUMNS: tuple[str, ...] = ("agecl", "racecl4")

AGE_LABELS = {1: "under 35", 2: "35-44", 3: "45-54", 4: "55-64", 5: "65-74", 6: "75 or older"}
RACE_LABELS = {
    1: "White non-Hispanic",
    2: "Black non-Hispanic",
    3: "Hispanic",
    4: "other or multiple race",
}


def cache_dir() -> Path:
    return Path(os.environ.get("WEALTHDATA_CACHE", Path.home() / ".cache" / "wealthdata"))


def pins() -> dict[str, dict]:
    return json.loads(PINS_PATH.read_text()) if PINS_PATH.exists() else {}


def extract_path(year: int) -> Path:
    """Path of the cached zip for ``year``, downloading it if absent."""
    path = cache_dir() / "scf" / str(year) / f"scfp{year}s.zip"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        body, _ = fetch(EXTRACT_URL.format(year=year))
        path.write_bytes(body)
    return path


def pin(year: int) -> dict:
    """Download the extract for ``year`` and record its hash in the pins file."""
    if year not in WAVES:
        raise ValueError(f"{year} is not an SCF wave; expected one of {WAVES}")
    digest = hashlib.sha256(extract_path(year).read_bytes()).hexdigest()
    current = pins()
    entry = current.get(str(year))
    if entry and entry["sha256"] != digest:
        raise ValueError(
            f"the cached {year} extract ({digest[:12]}) differs from the pinned file "
            f"({entry['sha256'][:12]}); the Fed may have reissued it"
        )
    if not entry:
        current[str(year)] = {
            "url": EXTRACT_URL.format(year=year),
            "sha256": digest,
            "pinned_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        ordered = {key: current[key] for key in sorted(current)}
        PINS_PATH.write_text(json.dumps(ordered, indent=2) + "\n")
    return current[str(year)]


def load_wave(year: int) -> pd.DataFrame:
    """Return one SCF wave: all five implicates, one row per household-implicate.

    Columns: ``case`` (household id), ``implicate`` (1 to 5), ``wgt``, the
    :data:`DOLLAR_COLUMNS` and the :data:`GROUP_COLUMNS`. Rows are sorted by
    implicate, then case.
    """
    entry = pins().get(str(year))
    if entry is None:
        raise PermissionError(
            f"the {year} extract is not pinned in {PINS_PATH.name}; "
            f"run `python -m wealthdata.scf pin {year}` to open it"
        )
    path = extract_path(year)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(
            f"{path} has SHA-256 {digest[:12]}, expected {entry['sha256'][:12]}; "
            "the Fed may have reissued the extract"
        )
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".dta")]
        if len(members) != 1:
            raise ValueError(f"expected one .dta in {path.name}, found {members}")
        raw = pd.read_stata(io.BytesIO(archive.read(members[0])), convert_categoricals=False)
    raw.columns = raw.columns.str.lower()
    # The 1989 file names its ids x1 and xx1; later waves use y1 and yy1.
    raw = raw.rename(columns={"x1": "y1", "xx1": "yy1"})
    needed = ("y1", "yy1", "wgt", *DOLLAR_COLUMNS, *GROUP_COLUMNS)
    missing = [column for column in needed if column not in raw.columns]
    if missing:
        raise KeyError(f"the {year} extract lacks column(s) {missing}")

    # y1 = yy1 * 10 + implicate. yy1 is stored as int16, so yy1 * 10 overflows
    # for case ids above 3276 unless both are widened first.
    case = raw["yy1"].astype("int64")
    implicate = raw["y1"].astype("int64") - case * 10
    if not implicate.isin(range(1, 6)).all():
        raise ValueError(f"unexpected implicate numbers in the {year} extract")

    wave = pd.DataFrame({"case": case, "implicate": implicate.astype("int8")})
    wave["wgt"] = raw["wgt"].astype("float64")
    for column in DOLLAR_COLUMNS:
        wave[column] = raw[column].astype("float64")
    for column in GROUP_COLUMNS:
        wave[column] = raw[column].astype("int8")
    if wave.isna().any().any():
        raise ValueError(f"missing values in the {year} extract")
    if not (wave["wgt"] > 0).all():
        raise ValueError(f"nonpositive weights in the {year} extract")
    counts = wave.groupby("case")["implicate"].nunique()
    if not (counts == 5).all():
        raise ValueError(f"some {year} households lack five implicates")
    wave = wave.sort_values(["implicate", "case"], kind="stable").reset_index(drop=True)
    return wave


def implicates(wave: pd.DataFrame) -> list[pd.DataFrame]:
    """Split a wave into its five implicate frames."""
    return [frame for _, frame in wave.groupby("implicate", sort=True)]


def _check_weights(wave: pd.DataFrame) -> None:
    totals = wave.groupby("implicate")["wgt"].sum().to_numpy()
    if not np.allclose(totals, totals[0], rtol=1e-9):
        raise ValueError("implicates carry different total weight")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "pin":
        raise SystemExit("usage: python -m wealthdata.scf pin YEAR [YEAR ...]")
    for argument in sys.argv[2:]:
        record = pin(int(argument))
        print(argument, record["sha256"][:12], record["pinned_utc"])
