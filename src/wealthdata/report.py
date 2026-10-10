"""Tables and figures for the report, built only from the files in ``results/``.

The Quarto document calls these functions, so every number in the report is
read from the committed results rather than typed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from wealthdata import aggregates, backtest, project, scf

RESULTS_DIR = backtest.RESULTS_DIR

CONTENDERS: dict[str, str] = {
    "a_no_change": "(a) No change",
    "b_uniform": "(b) Uniform",
    "c_asset_class": "(c) Asset class",
    "d_dfa_groups": "(d) DFA groups",
}
REAL_TIME = "d_dfa_groups_real_time"
#: Target waves for which a DFA vintage from before the SCF release exists.
REAL_TIME_TARGETS: tuple[int, ...] = tuple(aggregates.DFA_REAL_TIME_VINTAGE)

STAT_LABELS: dict[str, str] = {
    "mean": "Mean",
    "p10": "10th percentile",
    "p25": "25th percentile",
    "p50": "Median",
    "p75": "75th percentile",
    "p90": "90th percentile",
    "p99": "99th percentile",
    "top10_share": "Top 10% share",
    "top1_share": "Top 1% share",
    "gini": "Gini coefficient",
    **{f"median_age_{code}": f"Median, {label}" for code, label in scf.AGE_LABELS.items()},
    **{f"median_race_{code}": f"Median, {label}" for code, label in scf.RACE_LABELS.items()},
}
SCORE_LABELS = {
    "level": "Level (%)",
    "distribution": "Distribution (pp)",
    "subgroup": "Subgroup medians (%)",
}

#: Chart colors: the aging methods take the first three categorical slots of
#: the dataviz reference palette (validated together for color-vision
#: deficiency); doing nothing is the neutral baseline.
COLORS = {
    "a_no_change": "#898781",
    "b_uniform": "#2a78d6",
    "c_asset_class": "#eb6834",
    "d_dfa_groups": "#1baf7a",
}
MARKERS = {"a_no_change": "o", "b_uniform": "s", "c_asset_class": "^", "d_dfa_groups": "D"}
INK, SECONDARY, MUTED, GRID, AXIS, SURFACE = (
    "#0b0b0b",
    "#52514e",
    "#898781",
    "#e1e0d9",
    "#c3c2b7",
    "#fcfcfb",
)


def load(results_dir: Path = RESULTS_DIR) -> dict[str, pd.DataFrame]:
    names = ("scores", "scores_pooled", "summary", "factors", "wave_stats", "standard_errors")
    return {name: pd.read_csv(results_dir / f"{name}.csv") for name in names}


def last_pair(scores: pd.DataFrame) -> tuple[int, int]:
    target = int(scores["target"].max())
    return target - 3, target


def dollars(value: float) -> str:
    """Compact dollars: $29.6k, $216k, $1.24M, $15.0M."""
    magnitude = abs(value)
    if magnitude >= 1e6:
        return f"${value / 1e6:,.2f}M" if magnitude < 1e7 else f"${value / 1e6:,.1f}M"
    if magnitude >= 1e5:
        return f"${value / 1e3:,.0f}k"
    return f"${value / 1e3:,.1f}k"


def signed(value: float, digits: int = 1) -> str:
    return "n/a" if pd.isna(value) else f"{value:+.{digits}f}"


def wave_table(results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Actual net worth statistics by wave, in the extract's real dollars."""
    wide = results["wave_stats"].pivot(index="wave", columns="stat", values="value")
    table = pd.DataFrame(index=wide.index)
    table["Families (millions)"] = (wide["households"] / 1e6).map("{:.1f}".format)
    table["Sample"] = wide["sample_households"].map("{:,.0f}".format)
    for stat in ("mean", "p10", "p25", "p50", "p75", "p90", "p99"):
        table[STAT_LABELS[stat]] = wide[stat].map(dollars)
    for stat in ("top10_share", "top1_share"):
        table[STAT_LABELS[stat]] = (100 * wide[stat]).map("{:.1f}%".format)
    table[STAT_LABELS["gini"]] = wide["gini"].map("{:.3f}".format)
    return table.rename_axis("Wave")


def factor_table(results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Real per-household growth factors applied to each wave pair."""
    factors = results["factors"]
    rows = {}
    for (base, target), group in factors.groupby(["base", "target"]):
        by_method = {name: frame for name, frame in group.groupby("method")}
        row = {"Uniform": by_method["b_uniform"]["factor"].item()}
        classes = by_method["c_asset_class"].set_index("item")["factor"]
        for name in project.CLASSES:
            row[name.replace("_", " ").capitalize()] = classes[name]
        groups = by_method["d_dfa_groups"].set_index("item")["factor"]
        for name in project.DFA_GROUPS_5:
            row[f"{name} assets"] = groups[f"{name} assets"]
            row[f"{name} debt"] = groups[f"{name} debt"]
        rows[f"{base}→{target}"] = row
    return pd.DataFrame(rows).T.map("{:.3f}".format).rename_axis("Wave pair")


def score_table(results: dict[str, pd.DataFrame], methods: dict[str, str]) -> pd.DataFrame:
    """Mean of each summary score over all scored pairs, and pairs won."""
    summary = results["summary"]
    subset = summary[summary["method"].isin(methods)]
    table = pd.DataFrame(index=list(methods))
    for score, label in SCORE_LABELS.items():
        wide = subset[subset["score"] == score].pivot(
            index="target", columns="method", values="mean_abs_error"
        )[list(methods)]
        complete = wide.dropna()
        table[label] = complete.mean().map("{:.1f}".format)
        wins = complete.idxmin(axis=1).value_counts().reindex(list(methods), fill_value=0)
        table[f"{label} pairs won"] = wins.astype(int)
    table.index = [methods[name] for name in table.index]
    return table.rename_axis("Method")


def pair_score_table(
    results: dict[str, pd.DataFrame], score: str, methods: dict[str, str]
) -> pd.DataFrame:
    """One summary score for each wave pair and method."""
    summary = results["summary"]
    subset = summary[(summary["score"] == score) & summary["method"].isin(methods)]
    wide = subset.pivot(index="method", columns="target", values="mean_abs_error")
    wide = wide.reindex(list(methods))
    wide.columns = [f"{target - 3}→{str(target)[2:]}" for target in wide.columns]
    wide.index = [methods[name] for name in wide.index]
    return wide.map(lambda value: "" if pd.isna(value) else f"{value:.1f}").rename_axis("Method")


def real_time_table(results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Scores on the pairs where the DFA can be used as it stood at the time."""
    methods = {
        "a_no_change": "(a) No change",
        "b_uniform": "(b) Uniform",
        "c_asset_class": "(c) Asset class",
        REAL_TIME: "(d) DFA groups, real-time vintage",
    }
    summary = results["summary"]
    subset = summary[summary["method"].isin(methods) & summary["target"].isin(REAL_TIME_TARGETS)]
    wide = subset.pivot_table(index=["score", "method"], columns="target", values="mean_abs_error")
    frames = []
    for score, label in SCORE_LABELS.items():
        frame = wide.loc[score].reindex(list(methods))
        frame.insert(0, "Mean", frame.mean(axis=1))
        frame.columns = ["Mean", *[f"{target - 3}→{target}" for target in frame.columns[1:]]]
        frame.index = [methods[name] for name in frame.index]
        frame.insert(0, "Score", label)
        frames.append(frame)
    table = pd.concat(frames).rename_axis("Method").reset_index()
    numeric = table.columns[2:]
    table[numeric] = table[numeric].map(lambda value: "" if pd.isna(value) else f"{value:.1f}")
    return table[["Score", "Method", *numeric]]


def _noise_mark(z: float) -> str:
    return "" if pd.isna(z) or abs(z) < backtest.NOISE_THRESHOLD else "*"


def detail_table(
    results: dict[str, pd.DataFrame], base: int, target: int, stats: tuple[str, ...]
) -> pd.DataFrame:
    """Actual value and each contender's error for one wave pair.

    Errors are percent of the actual value for dollar statistics (percent of
    the actual median for the 10th percentile) and percentage points for
    shares and the Gini coefficient. An asterisk marks an error outside
    sampling noise.
    """
    scores = results["scores"]
    subset = scores[(scores["base"] == base) & (scores["target"] == target)]
    rows = []
    for stat in stats:
        of_stat = subset[subset["stat"] == stat].set_index("method")
        actual = of_stat["actual"].iloc[0]
        if stat in backtest.DISTRIBUTION_STATS:
            shown = f"{actual:.3f}" if stat == "gini" else f"{100 * actual:.1f}%"
        else:
            shown = dollars(actual)
        row = {"Statistic": STAT_LABELS[stat], f"Actual {target}": shown}
        for method, label in CONTENDERS.items():
            item = of_stat.loc[method]
            row[label] = signed(item["scaled_error"]) + _noise_mark(item["z"])
        rows.append(row)
    return pd.DataFrame(rows).set_index("Statistic")


def failure_table(results: dict[str, pd.DataFrame], stats: tuple[str, ...]) -> pd.DataFrame:
    """For each statistic and contender: mean signed error and pairs outside noise."""
    scores = results["scores"]
    pair_count = scores[["base", "target"]].drop_duplicates().shape[0]
    rows = []
    for stat in stats:
        row = {"Statistic": STAT_LABELS[stat]}
        for method, label in CONTENDERS.items():
            item = scores[(scores["stat"] == stat) & (scores["method"] == method)]
            outside = int((item["z"].abs() >= backtest.NOISE_THRESHOLD).sum())
            row[label] = (
                f"{signed(item['scaled_error'].mean())} / "
                f"{item['scaled_error'].abs().mean():.1f} / {outside} of {pair_count}"
            )
        rows.append(row)
    return pd.DataFrame(rows).set_index("Statistic")


def all_fail(results: dict[str, pd.DataFrame], stats: tuple[str, ...]) -> pd.DataFrame:
    """Wave pairs and statistics where every contender is outside noise."""
    scores = results["scores"]
    subset = scores[scores["method"].isin(CONTENDERS) & scores["stat"].isin(stats)]
    outside = subset.assign(outside=subset["z"].abs() >= backtest.NOISE_THRESHOLD)
    counts = outside.groupby(["base", "target", "stat"])["outside"].sum()
    failing = counts[counts == len(CONTENDERS)].reset_index()
    failing["Wave pair"] = failing["base"].astype(str) + "→" + failing["target"].astype(str)
    failing["Statistic"] = failing["stat"].map(STAT_LABELS)
    return failing[["Wave pair", "Statistic"]]


def published_check(results: dict[str, pd.DataFrame], published: dict[int, tuple[float, float]]):
    """Public-extract mean and median next to the Fed's published values."""
    waves = results["wave_stats"].set_index(["wave", "stat"])["value"]
    pooled = results["scores_pooled"]
    rows = []
    for year, (median, mean) in published.items():
        if (year, "mean") not in waves.index:
            continue
        stacked = pooled[(pooled["target"] == year) & (pooled["stat"] == "p50")]["actual"].iloc[0]
        for label, ours, theirs in (
            ("Mean", waves[(year, "mean")], mean * 1e3),
            ("Median, mean over implicates", waves[(year, "p50")], median * 1e3),
            ("Median, implicates stacked", stacked, median * 1e3),
        ):
            rows.append(
                {
                    "Wave": year,
                    "Statistic": label,
                    "Public extract": f"${ours / 1e3:,.1f}k",
                    "Fed Table 2": f"${theirs / 1e3:,.1f}k",
                    "Gap": f"{100 * (ours / theirs - 1):+.2f}%",
                }
            )
    return pd.DataFrame(rows).set_index(["Wave", "Statistic"])


def headline_figure(results: dict[str, pd.DataFrame], base: int, target: int):
    """Each contender's error at each point of the distribution, with noise.

    One column per statistic; a marker per contender at its error; a whisker
    of 1.96 standard errors of that error either side. Zero is the actual
    target-wave value.
    """
    import matplotlib.pyplot as plt

    stats = ("p10", "p25", "p50", "p75", "p90", "p99", "mean")
    scores = results["scores"]
    subset = scores[(scores["base"] == base) & (scores["target"] == target)]
    figure, axis = plt.subplots(figsize=(9.6, 5.4), dpi=200)
    figure.patch.set_facecolor(SURFACE)
    axis.set_facecolor(SURFACE)
    offsets = np.linspace(-0.27, 0.27, len(CONTENDERS))
    for offset, (method, label) in zip(offsets, CONTENDERS.items(), strict=True):
        of_method = subset[subset["method"] == method].set_index("stat").loc[list(stats)]
        scale = of_method["scaled_error"] / of_method["error"]
        half = backtest.NOISE_THRESHOLD * of_method["se_error"] * scale.abs()
        x = np.arange(len(stats)) + offset
        axis.vlines(
            x,
            of_method["scaled_error"] - half,
            of_method["scaled_error"] + half,
            color=COLORS[method],
            linewidth=1.2,
            alpha=0.55,
            zorder=2,
        )
        axis.scatter(
            x,
            of_method["scaled_error"],
            s=64 if MARKERS[method] == "^" else 46,
            marker=MARKERS[method],
            color=COLORS[method],
            edgecolor=SURFACE,
            linewidth=1.4,
            label=label,
            zorder=3,
        )
    axis.axhline(0, color=INK, linewidth=1.0, zorder=1)
    actual = subset[subset["method"] == "a_no_change"].set_index("stat")["actual"]
    labels = [
        f"{STAT_LABELS[stat].replace(' percentile', '')}\n{dollars(actual[stat])}" for stat in stats
    ]
    axis.set_xticks(np.arange(len(stats)), labels, color=SECONDARY, fontsize=9)
    axis.set_xlim(-0.6, len(stats) - 0.4)
    axis.yaxis.set_major_formatter(lambda value, _: f"{value:+.0f}%" if value else "0")
    axis.tick_params(axis="y", colors=MUTED, labelsize=9, length=0)
    axis.tick_params(axis="x", length=0, pad=8)
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(AXIS)
    axis.set_ylabel(
        f"Projected minus actual {target}, percent of actual", color=SECONDARY, fontsize=9
    )
    axis.text(
        len(stats) - 0.45,
        0,
        f" actual {target}",
        color=SECONDARY,
        fontsize=8.5,
        va="bottom",
        ha="right",
    )
    legend = axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=len(CONTENDERS),
        frameon=False,
        fontsize=9.5,
        handletextpad=0.3,
        columnspacing=1.6,
    )
    for text in legend.get_texts():
        text.set_color(INK)
    figure.tight_layout()
    return figure


def median_history_figure(results: dict[str, pd.DataFrame]):
    """Signed error in the projected median for every wave pair."""
    import matplotlib.pyplot as plt

    scores = results["scores"]
    subset = scores[(scores["stat"] == "p50") & scores["method"].isin(CONTENDERS)]
    wide = subset.pivot(index="target", columns="method", values="scaled_error")
    figure, axis = plt.subplots(figsize=(9.6, 4.2), dpi=200)
    figure.patch.set_facecolor(SURFACE)
    axis.set_facecolor(SURFACE)
    for method, label in CONTENDERS.items():
        axis.plot(
            wide.index,
            wide[method],
            color=COLORS[method],
            linewidth=2,
            marker=MARKERS[method],
            markersize=6.5,
            markeredgecolor=SURFACE,
            markeredgewidth=1.2,
            label=label,
            solid_capstyle="round",
        )
    axis.axhline(0, color=INK, linewidth=1.0, zorder=1)
    axis.set_xticks(list(wide.index), [f"{target - 3}→{str(target)[2:]}" for target in wide.index])
    axis.tick_params(axis="x", colors=SECONDARY, labelsize=8.5, length=0, pad=6)
    axis.tick_params(axis="y", colors=MUTED, labelsize=9, length=0)
    axis.yaxis.set_major_formatter(lambda value, _: f"{value:+.0f}%" if value else "0")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(AXIS)
    axis.set_ylabel("Projected minus actual median, percent", color=SECONDARY, fontsize=9)
    legend = axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.14),
        ncol=len(CONTENDERS),
        frameon=False,
        fontsize=9.5,
    )
    for text in legend.get_texts():
        text.set_color(INK)
    figure.tight_layout()
    return figure
