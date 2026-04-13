#!/usr/bin/env python3
"""Generate pruning-oriented plots from aggregated switch-box usage CSV files."""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Sequence, Tuple


HEADER_ROWS = 5
HEADER_COLS = 4
WIRE_SIDES = {"Left", "Right", "Top", "Bottom"}


@dataclass(frozen=True)
class SinkPattern:
    """Static information for one sink column from the actual switch pattern."""

    column_index: int
    label: str
    mux_size: int
    driver_rows: Tuple[int, ...]


@dataclass(frozen=True)
class DatasetAnalysis:
    """All derived pruning metrics for one aggregate CSV file."""

    name: str
    aggregate_path: Path
    total_wire_usage_percent: float
    edge_usage_values: List[float]
    edge_curve_x_percent: List[float]
    edge_curve_y_percent: List[float]
    topk_average_retention_percent: List[float]
    topk_min_retention_percent: List[float]
    topk_k_values: List[int]


@dataclass(frozen=True)
class FanoutRow:
    """Description of one source row in the switch-box matrix."""

    row_number: int
    side: str
    track_type: str
    track_coordinate: str
    tap: str


@dataclass(frozen=True)
class ReportConfig:
    """Plot and summary configuration, derived from the data and CLI input."""

    plot_dpi: int
    edge_percentiles_to_report: List[int]
    top_k_to_report: List[int]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for switch-block pruning analysis."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze one or more aggregate switch-box CSV files against the real "
            "switch pattern CSV and create pruning-oriented plots and summaries."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "aggregate_csvs",
        nargs="+",
        type=Path,
        help=(
            "One or more aggregate CSV files, for example "
            "/dsoft/amohaghegh/tap_util/run_dir/crr_2_0/koios/aggregate_switchbox_main.csv"
        ),
    )
    parser.add_argument(
        "--pattern-csv",
        required=True,
        type=Path,
        help=(
            "Actual switch pattern CSV that contains existing connections and delay "
            "values, for example "
            "/dsoft/amohaghegh/tap_util/device_data/crr_2_0/TURNKEY-FPGA3030/LVT/"
            "SSPG_0P72_125C/CSV/switchbox_main.csv"
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where plots and summary CSV files will be written",
    )
    parser.add_argument(
        "--labels",
        nargs="*",
        default=None,
        help="Optional labels for the aggregate CSVs, one label per input file",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=4,
        help="Decimal places to keep in summary CSV files",
    )
    parser.add_argument(
        "--plot-dpi",
        type=int,
        default=200,
        help="DPI to use when saving plots",
    )
    parser.add_argument(
        "--edge-percentiles",
        nargs="*",
        type=int,
        default=None,
        help=(
            "Optional top-edge percentages to report in the summary CSV. When "
            "omitted, the script derives them from the number of existing "
            "wire-to-wire switches"
        ),
    )
    parser.add_argument(
        "--top-k-report",
        nargs="*",
        type=int,
        default=None,
        help=(
            "Optional top-k sink-retention points to report in the summary CSV. "
            "When omitted, the script derives them from the actual mux sizes"
        ),
    )
    parser.add_argument(
        "--target-mux-size",
        type=int,
        default=None,
        help=(
            "Optional wire-to-wire mux size to keep per sink. When provided, the "
            "script writes a pruned copy of the pattern CSV by removing the "
            "lowest-used existing switches and then reruns the analysis on the "
            "pruned pattern"
        ),
    )
    return parser.parse_args()


def load_pyplot():
    """Import matplotlib with a writable cache path and a non-interactive backend."""
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("seaborn-v0_8-whitegrid")
    return plt


def read_csv_matrix(csv_path: Path) -> List[List[str]]:
    """Read a CSV file and pad rows so the matrix is rectangular."""
    with csv_path.open(newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        raise ValueError(f"{csv_path} is empty")

    width = max(len(row) for row in rows)
    if len(rows) < HEADER_ROWS or width < HEADER_COLS:
        raise ValueError(
            f"{csv_path} is too small to contain {HEADER_ROWS} header rows and "
            f"{HEADER_COLS} header columns"
        )

    return [row + [""] * (width - len(row)) for row in rows]


def cell_to_float(cell: str) -> float:
    """Convert a numeric-looking cell to float while treating blank cells as zero."""
    text = cell.strip()
    if not text:
        return 0.0

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"expected a numeric cell, found {cell!r}") from exc


def validate_same_layout(
    template_rows: Sequence[Sequence[str]],
    candidate_rows: Sequence[Sequence[str]],
    candidate_path: Path,
) -> None:
    """Ensure an aggregate CSV matches the pattern CSV layout and labels."""
    if len(template_rows) != len(candidate_rows):
        raise ValueError(
            f"{candidate_path} has {len(candidate_rows)} rows, expected "
            f"{len(template_rows)}"
        )

    if len(template_rows[0]) != len(candidate_rows[0]):
        raise ValueError(
            f"{candidate_path} has {len(candidate_rows[0])} columns, expected "
            f"{len(template_rows[0])}"
        )

    if list(template_rows[:HEADER_ROWS]) != list(candidate_rows[:HEADER_ROWS]):
        raise ValueError(
            f"{candidate_path} does not match the first {HEADER_ROWS} header rows "
            "of the pattern CSV"
        )

    for row_index, (template_row, candidate_row) in enumerate(
        zip(template_rows, candidate_rows),
        start=1,
    ):
        if list(template_row[:HEADER_COLS]) != list(candidate_row[:HEADER_COLS]):
            raise ValueError(
                f"{candidate_path} does not match the first {HEADER_COLS} header "
                f"columns on row {row_index}"
            )


def is_wire_side(side_label: str) -> bool:
    """Return True when the side label belongs to a wire, not IPIN/OPIN."""
    return side_label in WIRE_SIDES


def build_sink_patterns(pattern_rows: Sequence[Sequence[str]]) -> List[SinkPattern]:
    """Extract wire-to-wire sink columns and their current mux sizes from the pattern."""
    wire_row_indices = [
        row_index
        for row_index in range(HEADER_ROWS, len(pattern_rows))
        if is_wire_side(pattern_rows[row_index][0].strip())
    ]

    sink_patterns: List[SinkPattern] = []
    for column_index in range(HEADER_COLS, len(pattern_rows[0])):
        sink_side = pattern_rows[0][column_index].strip()
        if not is_wire_side(sink_side):
            continue

        # Only existing wire-to-wire connections contribute to the current mux size.
        driver_rows = tuple(
            row_index
            for row_index in wire_row_indices
            if pattern_rows[row_index][column_index].strip()
        )
        if not driver_rows:
            continue

        sink_patterns.append(
            SinkPattern(
                column_index=column_index,
                label=build_sink_label(pattern_rows, column_index),
                mux_size=len(driver_rows),
                driver_rows=driver_rows,
            )
        )

    if not sink_patterns:
        raise ValueError("pattern CSV contains no wire-to-wire sink columns")

    return sink_patterns


def build_sink_label(rows: Sequence[Sequence[str]], column_index: int) -> str:
    """Create a readable sink label from the header rows."""
    side = rows[0][column_index].strip()
    track_type = rows[1][column_index].strip()
    tap = rows[2][column_index].strip()
    bit = rows[3][column_index].strip()
    return f"{side}_{track_type}_tap{tap}_bit{bit}"


def build_row_label(rows: Sequence[Sequence[str]], row_index: int) -> str:
    """Create a readable source-row label from the row header columns."""
    side = rows[row_index][0].strip()
    track_type = rows[row_index][1].strip()
    track_coordinate = rows[row_index][2].strip()
    tap = rows[row_index][3].strip()
    return f"{side}_{track_type}_track{track_coordinate}_tap{tap}"


def build_edge_curve(edge_usage_values: Sequence[float]) -> Tuple[List[float], List[float]]:
    """Build the global edge concentration curve for one dataset."""
    if not edge_usage_values:
        raise ValueError("dataset contains no wire-to-wire edges")

    sorted_values = sorted(edge_usage_values, reverse=True)
    total_usage = sum(sorted_values)
    if total_usage <= 0.0:
        raise ValueError("dataset contains no wire-to-wire usage to analyze")

    cumulative_x: List[float] = []
    cumulative_y: List[float] = []
    running_total = 0.0
    for rank, usage_value in enumerate(sorted_values, start=1):
        running_total += usage_value
        cumulative_x.append((rank / len(sorted_values)) * 100.0)
        cumulative_y.append((running_total / total_usage) * 100.0)

    return cumulative_x, cumulative_y


def compute_topk_retention(
    sink_patterns: Sequence[SinkPattern],
    aggregate_rows: Sequence[Sequence[str]],
) -> Tuple[List[int], List[float], List[float]]:
    """Compute average and worst-case retained sink usage for top-k pruning."""
    max_mux_size = max(sink_pattern.mux_size for sink_pattern in sink_patterns)
    active_sink_usages: List[List[float]] = []

    for sink_pattern in sink_patterns:
        usage_values = sorted(
            (
                cell_to_float(aggregate_rows[row_index][sink_pattern.column_index])
                for row_index in sink_pattern.driver_rows
            ),
            reverse=True,
        )
        if sum(usage_values) > 0.0:
            active_sink_usages.append(usage_values)

    if not active_sink_usages:
        raise ValueError("aggregate CSV contains no active wire-to-wire sink columns")

    k_values = list(range(1, max_mux_size + 1))
    average_retention_percent: List[float] = []
    minimum_retention_percent: List[float] = []

    # Each sink is normalized independently because pruning is performed per sink mux.
    for keep_count in k_values:
        retained_shares: List[float] = []
        for usage_values in active_sink_usages:
            total_usage = sum(usage_values)
            retained_usage = sum(usage_values[:keep_count])
            retained_shares.append((retained_usage / total_usage) * 100.0)

        average_retention_percent.append(statistics.mean(retained_shares))
        minimum_retention_percent.append(min(retained_shares))

    return k_values, average_retention_percent, minimum_retention_percent


def analyze_dataset(
    name: str,
    aggregate_path: Path,
    aggregate_rows: Sequence[Sequence[str]],
    pattern_rows: Sequence[Sequence[str]],
    sink_patterns: Sequence[SinkPattern],
) -> DatasetAnalysis:
    """Compute all pruning metrics for one aggregate CSV."""
    validate_same_layout(pattern_rows, aggregate_rows, aggregate_path)

    edge_usage_values = [
        cell_to_float(aggregate_rows[row_index][sink_pattern.column_index])
        for sink_pattern in sink_patterns
        for row_index in sink_pattern.driver_rows
    ]
    edge_curve_x_percent, edge_curve_y_percent = build_edge_curve(edge_usage_values)
    k_values, topk_average_retention_percent, topk_min_retention_percent = (
        compute_topk_retention(sink_patterns, aggregate_rows)
    )

    return DatasetAnalysis(
        name=name,
        aggregate_path=aggregate_path,
        total_wire_usage_percent=sum(edge_usage_values),
        edge_usage_values=edge_usage_values,
        edge_curve_x_percent=edge_curve_x_percent,
        edge_curve_y_percent=edge_curve_y_percent,
        topk_average_retention_percent=topk_average_retention_percent,
        topk_min_retention_percent=topk_min_retention_percent,
        topk_k_values=k_values,
    )


def build_edge_usage_score_map(
    aggregate_rows_list: Sequence[Sequence[Sequence[str]]],
    sink_patterns: Sequence[SinkPattern],
) -> Dict[Tuple[int, int], float]:
    """Average switch usage across all provided aggregate CSV files.

    When more than one aggregate CSV is provided, pruning should not be driven by
    only one benchmark. We therefore rank each existing switch by its mean usage
    across all aggregate inputs.
    """
    score_map: Dict[Tuple[int, int], float] = {}

    for sink_pattern in sink_patterns:
        for row_index in sink_pattern.driver_rows:
            mean_usage = statistics.mean(
                cell_to_float(aggregate_rows[row_index][sink_pattern.column_index])
                for aggregate_rows in aggregate_rows_list
            )
            score_map[(row_index, sink_pattern.column_index)] = mean_usage

    return score_map


def prune_pattern_rows(
    pattern_rows: Sequence[Sequence[str]],
    sink_patterns: Sequence[SinkPattern],
    aggregate_rows_list: Sequence[Sequence[Sequence[str]]],
    target_mux_size: int,
) -> Tuple[List[List[str]], List[List[str]]]:
    """Create a pruned copy of the pattern CSV and list removed switches."""
    if target_mux_size <= 0:
        raise ValueError("--target-mux-size must be a positive integer")

    pruned_rows = [list(row) for row in pattern_rows]
    score_map = build_edge_usage_score_map(aggregate_rows_list, sink_patterns)
    removed_switch_rows: List[List[str]] = [
        [
            "sink_label",
            "source_row_number",
            "source_side",
            "source_track_type",
            "source_track_coordinate",
            "source_tap",
            "mean_usage_percent",
            "removed_rank_within_sink",
        ]
    ]

    for sink_pattern in sink_patterns:
        if sink_pattern.mux_size <= target_mux_size:
            continue

        switches_to_remove = sink_pattern.mux_size - target_mux_size
        # Remove the coldest existing switches first. Row index is a stable
        # secondary key so ties produce deterministic output.
        ranked_driver_rows = sorted(
            sink_pattern.driver_rows,
            key=lambda row_index: (
                score_map[(row_index, sink_pattern.column_index)],
                row_index,
            ),
        )

        for removal_rank, row_index in enumerate(ranked_driver_rows[:switches_to_remove], start=1):
            removed_switch_rows.append(
                [
                    sink_pattern.label,
                    str(row_index + 1),
                    pattern_rows[row_index][0].strip(),
                    pattern_rows[row_index][1].strip(),
                    pattern_rows[row_index][2].strip(),
                    pattern_rows[row_index][3].strip(),
                    format_float(score_map[(row_index, sink_pattern.column_index)], 6),
                    str(removal_rank),
                ]
            )
            pruned_rows[row_index][sink_pattern.column_index] = ""

    return pruned_rows, removed_switch_rows


def fanout_row_from_matrix(rows: Sequence[Sequence[str]], row_index: int) -> FanoutRow:
    """Build a structured description for one source row."""
    return FanoutRow(
        row_number=row_index + 1,
        side=rows[row_index][0].strip(),
        track_type=rows[row_index][1].strip(),
        track_coordinate=rows[row_index][2].strip(),
        tap=rows[row_index][3].strip(),
    )


def build_fanout_report_rows(
    no_wire_fanout_rows: Sequence[FanoutRow],
    no_any_fanout_rows: Sequence[FanoutRow],
) -> List[List[str]]:
    """Build a CSV report for source rows that lost fanout after pruning."""
    no_wire_lookup = {row.row_number for row in no_wire_fanout_rows}
    no_any_lookup = {row.row_number for row in no_any_fanout_rows}
    all_rows = sorted(
        {row.row_number: row for row in [*no_wire_fanout_rows, *no_any_fanout_rows]}.values(),
        key=lambda row: row.row_number,
    )

    report_rows = [
        [
            "row_number",
            "side",
            "track_type",
            "track_coordinate",
            "tap",
            "no_wire_to_wire_fanout",
            "no_fanout_anywhere",
        ]
    ]

    for row in all_rows:
        report_rows.append(
            [
                str(row.row_number),
                row.side,
                row.track_type,
                row.track_coordinate,
                row.tap,
                "yes" if row.row_number in no_wire_lookup else "no",
                "yes" if row.row_number in no_any_lookup else "no",
            ]
        )

    return report_rows


def find_rows_without_fanout(
    pattern_rows: Sequence[Sequence[str]],
) -> Tuple[List[FanoutRow], List[FanoutRow]]:
    """Find source rows with no remaining fanout after pruning.

    Two views are reported because wire-only pruning can leave a row with no
    wire-to-wire fanout while it still drives IPIN sinks.
    """
    wire_sink_columns = [
        column_index
        for column_index in range(HEADER_COLS, len(pattern_rows[0]))
        if is_wire_side(pattern_rows[0][column_index].strip())
    ]
    all_sink_columns = list(range(HEADER_COLS, len(pattern_rows[0])))

    no_wire_fanout_rows: List[FanoutRow] = []
    no_any_fanout_rows: List[FanoutRow] = []
    for row_index in range(HEADER_ROWS, len(pattern_rows)):
        if not is_wire_side(pattern_rows[row_index][0].strip()):
            continue

        has_wire_fanout = any(pattern_rows[row_index][column_index].strip() for column_index in wire_sink_columns)
        has_any_fanout = any(pattern_rows[row_index][column_index].strip() for column_index in all_sink_columns)

        if not has_wire_fanout:
            no_wire_fanout_rows.append(fanout_row_from_matrix(pattern_rows, row_index))
        if not has_any_fanout:
            no_any_fanout_rows.append(fanout_row_from_matrix(pattern_rows, row_index))

    return no_wire_fanout_rows, no_any_fanout_rows


def percentile_capture(edge_usage_values: Sequence[float], top_percent: int) -> float:
    """Return the retained usage when keeping the top N percent of edges globally."""
    sorted_values = sorted(edge_usage_values, reverse=True)
    total_usage = sum(sorted_values)
    if total_usage <= 0.0:
        return 0.0

    keep_count = max(1, math.ceil((top_percent / 100.0) * len(sorted_values)))
    return (sum(sorted_values[:keep_count]) / total_usage) * 100.0


def validate_positive_int(value: int, flag_name: str) -> None:
    """Validate that a CLI integer option is positive."""
    if value <= 0:
        raise ValueError(f"{flag_name} must be a positive integer")


def derive_edge_percentiles(edge_count: int) -> List[int]:
    """Derive useful report percentiles from the number of existing switches.

    The percentages are chosen from powers of two in edge-count space, then
    converted to percentages. This keeps the report adaptive to the actual size
    of the switch graph instead of relying on a fixed hard-coded list.
    """
    if edge_count <= 0:
        raise ValueError("edge count must be positive when deriving percentiles")

    derived_percentiles = set()
    keep_count = 1
    while keep_count < edge_count:
        derived_percentiles.add(max(1, math.ceil((keep_count / edge_count) * 100.0)))
        keep_count *= 2

    derived_percentiles.add(100)
    return sorted(derived_percentiles)


def normalize_edge_percentiles(
    requested_percentiles: Sequence[int] | None,
    edge_count: int,
) -> List[int]:
    """Return validated report percentiles, deriving them from the data if needed."""
    if requested_percentiles is None:
        return derive_edge_percentiles(edge_count)

    normalized = sorted(set(requested_percentiles))
    for percentile in normalized:
        if percentile <= 0 or percentile > 100:
            raise ValueError("--edge-percentiles values must be in the range 1..100")
    return normalized


def value_at_k(values: Sequence[float], k: int) -> float:
    """Return the top-k curve value, clamping at the largest available k."""
    if not values:
        return 0.0
    clamped_index = min(k, len(values)) - 1
    return values[clamped_index]


def normalize_top_k_report(
    requested_top_k: Sequence[int] | None,
    max_mux_size: int,
) -> List[int]:
    """Return validated top-k report points, deriving them from the data if needed."""
    if max_mux_size <= 0:
        raise ValueError("max mux size must be positive when deriving top-k values")

    if requested_top_k is None:
        return list(range(1, max_mux_size + 1))

    normalized = sorted(set(requested_top_k))
    for top_k in normalized:
        if top_k <= 0:
            raise ValueError("--top-k-report values must be positive integers")
        if top_k > max_mux_size:
            raise ValueError(
                f"--top-k-report value {top_k} exceeds the maximum mux size of {max_mux_size}"
            )
    return normalized


def build_report_config(
    analyses: Sequence[DatasetAnalysis],
    sink_patterns: Sequence[SinkPattern],
    plot_dpi: int,
    requested_edge_percentiles: Sequence[int] | None,
    requested_top_k: Sequence[int] | None,
) -> ReportConfig:
    """Build report settings from the data shape and optional user overrides."""
    validate_positive_int(plot_dpi, "--plot-dpi")

    max_edge_count = max(len(analysis.edge_usage_values) for analysis in analyses)
    max_mux_size = max(sink_pattern.mux_size for sink_pattern in sink_patterns)

    return ReportConfig(
        plot_dpi=plot_dpi,
        edge_percentiles_to_report=normalize_edge_percentiles(
            requested_edge_percentiles,
            max_edge_count,
        ),
        top_k_to_report=normalize_top_k_report(
            requested_top_k,
            max_mux_size,
        ),
    )


def build_summary_rows(
    analyses: Sequence[DatasetAnalysis],
    sink_patterns: Sequence[SinkPattern],
    precision: int,
    report_config: ReportConfig,
) -> List[List[str]]:
    """Build a compact CSV summary of the most useful pruning metrics."""
    mux_sizes = [sink_pattern.mux_size for sink_pattern in sink_patterns]
    header_row = [
        "dataset",
        "aggregate_csv",
        "wire_sink_count",
        "average_wire_mux_size",
        "max_wire_mux_size",
        "wire_to_wire_usage_percent",
    ]
    header_row.extend(
        f"top_{top_percent}_percent_edges_capture_percent"
        for top_percent in report_config.edge_percentiles_to_report
    )
    for top_k in report_config.top_k_to_report:
        header_row.append(f"top_{top_k}_average_sink_retention_percent")
        header_row.append(f"top_{top_k}_min_sink_retention_percent")

    rows = [header_row]

    for analysis in analyses:
        row = [
            analysis.name,
            str(analysis.aggregate_path),
            str(len(sink_patterns)),
            format_float(statistics.mean(mux_sizes), precision),
            format_float(max(mux_sizes), precision),
            format_float(analysis.total_wire_usage_percent, precision),
        ]

        for top_percent in report_config.edge_percentiles_to_report:
            row.append(
                format_float(
                    percentile_capture(analysis.edge_usage_values, top_percent),
                    precision,
                )
            )

        for top_k in report_config.top_k_to_report:
            row.append(
                format_float(
                    value_at_k(analysis.topk_average_retention_percent, top_k),
                    precision,
                )
            )
            row.append(
                format_float(
                    value_at_k(analysis.topk_min_retention_percent, top_k),
                    precision,
                )
            )

        rows.append(row)

    return rows


def build_mux_size_rows(sink_patterns: Sequence[SinkPattern], precision: int) -> List[List[str]]:
    """Build a pattern-only CSV summary for current wire-to-wire mux sizes."""
    mux_histogram = Counter(sink_pattern.mux_size for sink_pattern in sink_patterns)
    rows = [["mux_size", "sink_count"]]

    for mux_size in sorted(mux_histogram):
        rows.append([format_float(mux_size, precision), str(mux_histogram[mux_size])])

    return rows


def format_float(value: float, precision: int) -> str:
    """Format floats compactly while keeping a consistent precision limit."""
    text = f"{value:.{precision}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def write_csv(rows: Sequence[Sequence[str]], output_path: Path) -> None:
    """Write a CSV file to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def plot_edge_concentration(
    plt,
    analyses: Sequence[DatasetAnalysis],
    output_path: Path,
    plot_dpi: int,
) -> None:
    """Plot how much usage is captured by the hottest global edges."""
    figure, axis = plt.subplots(figsize=(8, 5))

    for analysis in analyses:
        axis.plot(
            analysis.edge_curve_x_percent,
            analysis.edge_curve_y_percent,
            linewidth=2,
            label=analysis.name,
        )

    axis.axvline(10.0, color="gray", linestyle="--", linewidth=1)
    axis.axvline(20.0, color="gray", linestyle=":", linewidth=1)
    axis.set_xlabel("Top existing wire-to-wire switches kept (%)")
    axis.set_ylabel("Wire-to-wire usage retained (%)")
    axis.set_title("Global Edge Usage Concentration")
    axis.set_xlim(0, 100)
    axis.set_ylim(0, 100)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=plot_dpi)
    plt.close(figure)


def plot_topk_retention(
    plt,
    analyses: Sequence[DatasetAnalysis],
    output_path: Path,
    metric_name: str,
    y_label: str,
    title: str,
    plot_dpi: int,
) -> None:
    """Plot sink-local retained usage while keeping only the top-k drivers."""
    figure, axis = plt.subplots(figsize=(8, 5))

    for analysis in analyses:
        values = (
            analysis.topk_average_retention_percent
            if metric_name == "average"
            else analysis.topk_min_retention_percent
        )
        axis.plot(
            analysis.topk_k_values,
            values,
            marker="o",
            linewidth=2,
            label=analysis.name,
        )

    axis.set_xlabel("Top-k wire-to-wire drivers kept per sink")
    axis.set_ylabel(y_label)
    axis.set_title(title)
    axis.set_xlim(left=1)
    axis.set_ylim(0, 100)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=plot_dpi)
    plt.close(figure)


def plot_mux_histogram(
    plt,
    sink_patterns: Sequence[SinkPattern],
    output_path: Path,
    plot_dpi: int,
) -> None:
    """Plot the current wire-to-wire mux size distribution from the pattern file."""
    mux_histogram = Counter(sink_pattern.mux_size for sink_pattern in sink_patterns)
    mux_sizes = sorted(mux_histogram)
    total_sink_count = len(sink_patterns)
    sink_percentages = [
        (mux_histogram[mux_size] / total_sink_count) * 100.0 for mux_size in mux_sizes
    ]

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.bar(mux_sizes, sink_percentages, width=0.8, color="#4C78A8")
    axis.set_xlabel("Current wire-to-wire mux size")
    axis.set_ylabel("Sink columns (%)")
    axis.set_title("Pattern Wire-to-Wire Mux Size Distribution")
    axis.set_xticks(mux_sizes)
    axis.set_ylim(0, 100)
    figure.tight_layout()
    figure.savefig(output_path, dpi=plot_dpi)
    plt.close(figure)


def build_default_output_dir(first_aggregate_path: Path, pattern_csv: Path) -> Path:
    """Choose a stable default output directory beside the first aggregate CSV."""
    return first_aggregate_path.parent / f"pruning_analysis_{pattern_csv.stem}"


def build_pruned_output_dir(output_dir: Path, target_mux_size: int) -> Path:
    """Choose the output directory for pruned-pattern analysis."""
    return output_dir / f"pruned_keep_{target_mux_size}"


def derive_dataset_names(
    aggregate_paths: Sequence[Path],
    labels: Sequence[str] | None,
) -> List[str]:
    """Create human-readable dataset labels, with optional user overrides."""
    if labels is not None:
        if len(labels) != len(aggregate_paths):
            raise ValueError("the number of --labels entries must match aggregate CSV files")
        return list(labels)

    raw_names = []
    for aggregate_path in aggregate_paths:
        if aggregate_path.stem.startswith("aggregate_"):
            raw_names.append(aggregate_path.parent.name or aggregate_path.stem)
        else:
            raw_names.append(aggregate_path.stem)

    name_counts = Counter(raw_names)
    seen_counts: DefaultDict[str, int] = defaultdict(int)
    dataset_names: List[str] = []
    for raw_name in raw_names:
        if name_counts[raw_name] == 1:
            dataset_names.append(raw_name)
            continue

        seen_counts[raw_name] += 1
        dataset_names.append(f"{raw_name}_{seen_counts[raw_name]}")

    return dataset_names


def generate_outputs(
    analyses: Sequence[DatasetAnalysis],
    sink_patterns: Sequence[SinkPattern],
    output_dir: Path,
    precision: int,
    report_config: ReportConfig,
) -> List[Path]:
    """Write summary CSV files and plot images to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt = load_pyplot()

    output_paths = [
        output_dir / "edge_usage_concentration.png",
        output_dir / "topk_average_sink_retention.png",
        output_dir / "topk_min_sink_retention.png",
        output_dir / "pattern_wire_mux_size_histogram.png",
        output_dir / "pruning_summary.csv",
        output_dir / "pattern_mux_size_summary.csv",
    ]

    plot_edge_concentration(plt, analyses, output_paths[0], report_config.plot_dpi)
    plot_topk_retention(
        plt,
        analyses,
        output_paths[1],
        metric_name="average",
        y_label="Average sink usage retained (%)",
        title="Average Retained Usage After Per-Sink Top-k Pruning",
        plot_dpi=report_config.plot_dpi,
    )
    plot_topk_retention(
        plt,
        analyses,
        output_paths[2],
        metric_name="minimum",
        y_label="Worst-case sink usage retained (%)",
        title="Worst-Case Retained Usage After Per-Sink Top-k Pruning",
        plot_dpi=report_config.plot_dpi,
    )
    plot_mux_histogram(plt, sink_patterns, output_paths[3], report_config.plot_dpi)
    write_csv(
        build_summary_rows(analyses, sink_patterns, precision, report_config),
        output_paths[4],
    )
    write_csv(build_mux_size_rows(sink_patterns, precision), output_paths[5])

    return output_paths


def write_matrix_csv(rows: Sequence[Sequence[str]], output_path: Path) -> None:
    """Write a rectangular CSV matrix back to disk."""
    write_csv(rows, output_path)


def print_fanout_rows(
    header: str,
    rows: Sequence[FanoutRow],
) -> None:
    """Print a concise fanout summary to stdout."""
    print(f"{header}: {len(rows)}")
    for row in rows:
        print(
            f"  row {row.row_number}: {row.side},{row.track_type},"
            f"{row.track_coordinate},{row.tap}"
        )


def main() -> int:
    """Program entry point."""
    args = parse_args()

    try:
        aggregate_paths = [aggregate_path.resolve() for aggregate_path in args.aggregate_csvs]
        pattern_csv = args.pattern_csv.resolve()
        output_dir = (
            args.output_dir.resolve()
            if args.output_dir is not None
            else build_default_output_dir(aggregate_paths[0], pattern_csv).resolve()
        )

        if not pattern_csv.is_file():
            print(f"error: pattern CSV does not exist: {pattern_csv}", file=sys.stderr)
            return 1

        for aggregate_path in aggregate_paths:
            if not aggregate_path.is_file():
                print(f"error: aggregate CSV does not exist: {aggregate_path}", file=sys.stderr)
                return 1

        dataset_names = derive_dataset_names(aggregate_paths, args.labels)
        pattern_rows = read_csv_matrix(pattern_csv)
        sink_patterns = build_sink_patterns(pattern_rows)
        if args.target_mux_size is not None:
            if args.target_mux_size <= 0:
                raise ValueError("--target-mux-size must be a positive integer")

        analyses: List[DatasetAnalysis] = []
        aggregate_rows_list: List[List[List[str]]] = []
        for dataset_name, aggregate_path in zip(dataset_names, aggregate_paths):
            aggregate_rows = read_csv_matrix(aggregate_path)
            aggregate_rows_list.append(aggregate_rows)
            analyses.append(
                analyze_dataset(
                    dataset_name,
                    aggregate_path,
                    aggregate_rows,
                    pattern_rows,
                    sink_patterns,
                )
            )

        output_paths = generate_outputs(
            analyses,
            sink_patterns,
            output_dir,
            args.precision,
            build_report_config(
                analyses,
                sink_patterns,
                args.plot_dpi,
                args.edge_percentiles,
                args.top_k_report,
            ),
        )

        pruned_output_paths: List[Path] = []
        pruned_pattern_output_path: Path | None = None
        fanout_report_path: Path | None = None
        removed_switches_path: Path | None = None
        no_wire_fanout_rows: List[FanoutRow] = []
        no_any_fanout_rows: List[FanoutRow] = []

        if args.target_mux_size is not None:
            pruned_output_dir = build_pruned_output_dir(output_dir, args.target_mux_size)
            pruned_rows, removed_switch_rows = prune_pattern_rows(
                pattern_rows,
                sink_patterns,
                aggregate_rows_list,
                args.target_mux_size,
            )
            pruned_pattern_output_path = pruned_output_dir / pattern_csv.name
            write_matrix_csv(pruned_rows, pruned_pattern_output_path)
            removed_switches_path = pruned_output_dir / "removed_switches.csv"
            write_csv(removed_switch_rows, removed_switches_path)
            pruned_sink_patterns = build_sink_patterns(pruned_rows)
            pruned_analyses = [
                analyze_dataset(
                    analysis.name,
                    analysis.aggregate_path,
                    aggregate_rows,
                    pruned_rows,
                    pruned_sink_patterns,
                )
                for analysis, aggregate_rows in zip(analyses, aggregate_rows_list)
            ]
            pruned_output_paths = generate_outputs(
                pruned_analyses,
                pruned_sink_patterns,
                pruned_output_dir,
                args.precision,
                build_report_config(
                    pruned_analyses,
                    pruned_sink_patterns,
                    args.plot_dpi,
                    args.edge_percentiles,
                    args.top_k_report,
                ),
            )
            no_wire_fanout_rows, no_any_fanout_rows = find_rows_without_fanout(pruned_rows)
            fanout_report_path = pruned_output_dir / "rows_without_fanout.csv"
            write_csv(
                build_fanout_report_rows(no_wire_fanout_rows, no_any_fanout_rows),
                fanout_report_path,
            )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Analyzed {len(analyses)} aggregate CSV file(s).")
    print(f"Output directory: {output_dir}")
    for output_path in output_paths:
        print(f"Wrote: {output_path}")
    if pruned_pattern_output_path is not None:
        print(f"Wrote: {pruned_pattern_output_path}")
        if removed_switches_path is not None:
            print(f"Wrote: {removed_switches_path}")
        for output_path in pruned_output_paths:
            print(f"Wrote: {output_path}")
        if fanout_report_path is not None:
            print(f"Wrote: {fanout_report_path}")
        print_fanout_rows("Rows without remaining wire-to-wire fanout", no_wire_fanout_rows)
        print_fanout_rows("Rows without any remaining fanout", no_any_fanout_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
