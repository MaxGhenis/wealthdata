# ruff: noqa: E501
"""Mutation check: each deliberate fault must make some test fail.

Copies the repository to a scratch directory (never edits this checkout),
injects one fault at a time, and runs the tests most likely to catch it.

    uv run python scripts/mutation_check.py [WORKDIR]
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()) / "wealthdata"
PY = REPO / ".venv/bin/python"

MUTATIONS = [
    (
        "project.py",
        '    projected["networth"] = net_worth(projected)\n    return projected',
        '    projected["networth"] = net_worth(projected)\n    projected["wgt"] = projected["wgt"] * 1.0000001\n    return projected',
        "weights nudged",
        ["test_project.py"],
    ),
    (
        "project.py",
        "return _scaled(sheet, np.array([[float(factors[name]) for name in CLASSES]]))",
        "return _scaled(sheet, np.array([[float(factors[name]) for name in reversed(CLASSES)]]))",
        "class factors misordered",
        ["test_project.py"],
    ),
    (
        "project.py",
        'return sheet[list(ASSET_CLASSES)].sum(axis=1) - sheet["debt"]',
        'return sheet[list(ASSET_CLASSES)].sum(axis=1) + sheet["debt"]',
        "debt added to net worth",
        ["test_project.py", "test_scf.py"],
    ),
    (
        "project.py",
        "midpoint = (cumulative - w[order] / 2.0) / cumulative[-1]",
        "midpoint = (cumulative - w[order] * 2.0) / cumulative[-1]",
        "group midpoint shifted",
        ["test_project.py"],
    ),
    (
        "project.py",
        "order = np.lexsort((np.asarray(tiebreak), x))",
        "order = np.lexsort((np.asarray(tiebreak), -x))",
        "groups ranked richest first",
        ["test_project.py"],
    ),
    (
        "stats.py",
        'side="left")), x.size - 1)',
        'side="right")), x.size - 1)',
        "quantile takes next observation at ties",
        ["test_stats.py"],
    ),
    (
        "stats.py",
        "return float(1.0 - 2.0 * area)",
        "return float(1.0 - 1.9 * area)",
        "gini area coefficient",
        ["test_stats.py"],
    ),
    (
        "stats.py",
        "return float(1.0 - np.interp(1.0 - fraction, population, wealth))",
        "return float(1.0 - np.interp(fraction, population, wealth))",
        "top share uses bottom cutoff",
        ["test_stats.py"],
    ),
    (
        "stats.py",
        "float(np.mean([item[key] for item in per_implicate]))",
        "float(np.median([item[key] for item in per_implicate]))",
        "implicates combined by median",
        ["test_stats.py", "test_backtest.py"],
    ),
    (
        "aggregates.py",
        "factor = nominal_ratio / price_ratio(base, target)",
        "factor = nominal_ratio * price_ratio(base, target)",
        "deflator multiplied",
        ["test_aggregates.py", "test_backtest.py"],
    ),
    (
        "aggregates.py",
        "factor /= household_ratio(base, target)",
        "factor *= household_ratio(base, target)",
        "household growth multiplied",
        ["test_aggregates.py"],
    ),
    (
        "aggregates.py",
        "return float(levels[label(target, quarter)] / levels[label(base, quarter)])",
        "return float(levels[label(base, quarter)] / levels[label(target, quarter)])",
        "growth ratio inverted",
        ["test_aggregates.py", "test_backtest.py"],
    ),
    (
        "aggregates.py",
        "DEFAULT_QUARTER = 3",
        "DEFAULT_QUARTER = 4",
        "default quarter",
        ["test_aggregates.py", "test_backtest.py"],
    ),
    (
        "backtest.py",
        'scaled = 100.0 * error / actual["p50"]',
        "scaled = 100.0 * error / truth",
        "p10 scaled by itself",
        ["test_backtest.py"],
    ),
    (
        "backtest.py",
        'merged["se_error"] = np.sqrt(merged["se_projected"] ** 2 + merged["se_actual"] ** 2)',
        'merged["se_error"] = merged["se_projected"] + merged["se_actual"]',
        "standard errors added linearly",
        ["test_backtest.py"],
    ),
    (
        "replicates.py",
        '"se": np.sqrt(6.0 / 5.0 * imputation + sampling),',
        '"se": np.sqrt(imputation + sampling),',
        "imputation variance not inflated",
        ["test_backtest.py"],
    ),
    (
        "replicates.py",
        'multiplicity = raw[[f"mm{i}" for i in numbers]].to_numpy(dtype="float64")',
        'multiplicity = raw[[f"mm{i}" for i in reversed(numbers)]].to_numpy(dtype="float64")',
        "replicate multiplicities mispaired",
        ["test_scf.py", "test_backtest.py"],
    ),
    (
        "scf.py",
        'case = raw["yy1"].astype("int64")\n    implicate = raw["y1"].astype("int64") - case * 10',
        'case = raw["yy1"]\n    implicate = raw["y1"].astype("int64") - (case * 10).astype("int64")',
        "int16 overflow in implicate",
        ["test_scf.py"],
    ),
]

if WORK.exists():
    shutil.rmtree(WORK)
shutil.copytree(
    REPO,
    WORK,
    ignore=shutil.ignore_patterns(
        ".venv", ".git", "report", "__pycache__", ".pytest_cache", ".hypothesis"
    ),
)
conftest = WORK / "tests/conftest.py"
conftest.write_text(conftest.read_text().replace("max_examples=200", "max_examples=60"))
env = {**os.environ, "PYTHONPATH": str(WORK / "src")}
check = subprocess.run(
    [str(PY), "-c", "import wealthdata; print(wealthdata.__file__)"],
    env=env,
    capture_output=True,
    text=True,
    cwd=WORK,
)
print("imports from:", check.stdout.strip(), flush=True)
assert str(WORK) in check.stdout, "copy is not the module being tested"

baseline = subprocess.run(
    [str(PY), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"],
    cwd=WORK,
    env=env,
    capture_output=True,
    text=True,
)
print("baseline:", baseline.stdout.strip().splitlines()[-1], flush=True)
assert baseline.returncode == 0

survivors = []
for name, old, new, label, files in MUTATIONS:
    path = WORK / "src/wealthdata" / name
    original = path.read_text()
    if original.count(old) != 1:
        print(f"NOT APPLIED ({original.count(old)} matches): {label}", flush=True)
        survivors.append(label + " [not applied]")
        continue
    path.write_text(original.replace(old, new))
    run = subprocess.run(
        [
            str(PY),
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            *[f"tests/{f}" for f in files],
        ],
        cwd=WORK,
        env=env,
        capture_output=True,
        text=True,
    )
    path.write_text(original)
    failed = [line for line in run.stdout.splitlines() if line.startswith(("FAILED", "ERROR"))]
    killed = run.returncode != 0
    print(
        ("KILLED   " if killed else "SURVIVED ")
        + label
        + (f"  <- {failed[0][:120]}" if failed else ""),
        flush=True,
    )
    if not killed:
        survivors.append(label)
print("SURVIVORS:", survivors, flush=True)
sys.exit(1 if survivors else 0)
