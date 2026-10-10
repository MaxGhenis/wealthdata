"""Standard errors from the SCF replicate weights.

Follows the SCF codebook's ``MEANIT`` program: the sampling variance of a
statistic is its variance across 999 replicate-weight estimates on the first
implicate, the imputation variance is its variance across the five implicate
estimates, and the total standard error is
``sqrt(6/5 * imputation variance + sampling variance)``.

A replicate weight is the file's weight times its multiplicity (the number
of times the household was drawn into that replicate); households not drawn
have weight zero and drop out.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from wealthdata import scf, stats
from wealthdata.sources import fetch

REPLICATE_COUNT = 999

PINS_PATH = Path(__file__).resolve().parents[2] / "data" / "scf_replicate_weights.json"


def url(year: int) -> str:
    stem = f"scf{str(year)[2:]}rw1s" if year <= 1998 else f"scf{year}rw1s"
    return f"https://www.federalreserve.gov/econres/files/{stem}.zip"


def pins() -> dict[str, dict]:
    return json.loads(PINS_PATH.read_text()) if PINS_PATH.exists() else {}


def _path(year: int) -> Path:
    path = scf.cache_dir() / "scf_replicates" / str(year) / url(year).rsplit("/", 1)[1]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        body, _ = fetch(url(year))
        path.write_bytes(body)
    return path


def pin(year: int) -> dict:
    """Download the replicate weights for ``year`` and record the file's hash."""
    if str(year) not in scf.pins():
        raise PermissionError(f"pin the {year} extract before its replicate weights")
    digest = hashlib.sha256(_path(year).read_bytes()).hexdigest()
    current = pins()
    entry = current.get(str(year))
    if entry and entry["sha256"] != digest:
        raise ValueError(f"the cached {year} replicate weights differ from the pinned file")
    if not entry:
        current[str(year)] = {
            "url": url(year),
            "sha256": digest,
            "pinned_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        ordered = {key: current[key] for key in sorted(current)}
        PINS_PATH.write_text(json.dumps(ordered, indent=2) + "\n")
    return current[str(year)]


def load(year: int) -> pd.DataFrame:
    """Replicate weights (weight times multiplicity), one row per household.

    Indexed by ``case``; columns are replicates 1 to 999.
    """
    entry = pins().get(str(year))
    if entry is None:
        raise PermissionError(f"the {year} replicate weights are not pinned")
    path = _path(year)
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError(f"{path} does not match its pinned hash")
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".dta")]
        if len(members) != 1:
            raise ValueError(f"expected one .dta in {path.name}, found {members}")
        raw = pd.read_stata(io.BytesIO(archive.read(members[0])), convert_categoricals=False)
    raw.columns = raw.columns.str.lower()
    raw = raw.rename(columns={"x1": "y1", "xx1": "yy1"})
    numbers = range(1, REPLICATE_COUNT + 1)
    weight = raw[[f"wt1b{i}" for i in numbers]].to_numpy(dtype="float64")
    multiplicity = raw[[f"mm{i}" for i in numbers]].to_numpy(dtype="float64")
    product = np.nan_to_num(np.maximum(weight, 0.0)) * np.nan_to_num(np.maximum(multiplicity, 0.0))
    table = pd.DataFrame(product, index=raw["yy1"].astype("int64").rename("case"), columns=numbers)
    if not table.index.is_unique:
        raise ValueError(f"duplicate households in the {year} replicate weights")
    return table.sort_index()


def standard_errors(
    sheet: pd.DataFrame,
    replicate_weights: pd.DataFrame,
    *,
    projector: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    reproject: bool = False,
    statistic: Callable[[pd.DataFrame], dict[str, float]] = stats.summary,
) -> pd.DataFrame:
    """Standard errors of ``statistic`` on ``sheet``, optionally after projecting it.

    ``projector`` maps a balance sheet to its projection. With ``reproject``
    the projection is redone under each replicate's weights, which matters
    when the projection itself depends on the weights (wealth groups are
    assigned by weighted rank).

    Returns one row per statistic: the estimate (mean over implicates), the
    imputation and sampling standard deviations, and the total standard error.
    """
    apply = projector if projector is not None else (lambda frame: frame)
    projected = apply(sheet)
    by_implicate = pd.DataFrame(
        [statistic(group) for _, group in projected.groupby("implicate", sort=True)]
    )

    first = sheet[sheet["implicate"] == 1]
    weights = replicate_weights.reindex(first["case"].to_numpy())
    if weights.isna().any().any():
        raise ValueError("replicate weights are missing for some households")
    matrix = weights.to_numpy()
    first_projected = None if reproject else apply(first)
    rows = []
    for column in range(matrix.shape[1]):
        keep = matrix[:, column] > 0
        if reproject:
            draw = first.loc[keep].copy()
            draw["wgt"] = matrix[keep, column]
            draw = apply(draw)
        else:
            draw = first_projected.loc[keep].copy()
            draw["wgt"] = matrix[keep, column]
        rows.append(statistic(draw))
    by_replicate = pd.DataFrame(rows)

    imputation = by_implicate.var(ddof=1)
    sampling = by_replicate.var(ddof=1)
    return pd.DataFrame(
        {
            "estimate": by_implicate.mean(),
            "sd_imputation": np.sqrt(imputation),
            "sd_sampling": np.sqrt(sampling),
            "se": np.sqrt(6.0 / 5.0 * imputation + sampling),
        }
    ).rename_axis("stat")
