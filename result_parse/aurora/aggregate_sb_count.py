#!/usr/bin/env python3
"""Aggregate switch-box usage CSV files under a run directory."""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, List, Sequence, Tuple


HEADER_ROWS = 5
HEADER_COLS = 4
PERCENT_SCALE = 100.0
WIRE_SIDES = {"Left", "Right", "Top", "Bottom"}
INCREMENTAL_WIRE_SIDES = {"Left", "Bottom"}
DECREMENTAL_WIRE_SIDES = {"Right", "Top"}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for switch-box aggregation."""
    parser = argparse.ArgumentParser(
        description=(
            "Recursively search a run directory for sb_count CSV files with the "
            "requested name, convert each file to connection percentages, and "
            "write the cell-wise average to a new aggregate CSV."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help=(
            "Root directory to search, for example a single seed directory like "
            "/dsoft/amohaghegh/tap_util/run_dir/crr_2_0/koios/seed_1 or a "
            "multi-seed directory like /dsoft/amohaghegh/tap_util/run_dir/crr_2_0/koios"
        ),
    )
    parser.add_argument(
        "switch_block_pattern",
        help="Switch block CSV filename to aggregate, for example switchbox_main.csv",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory where aggregated CSV files will be written. In multi-seed "
            "mode, one subdirectory per seed is created under this path"
        ),
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=10,
        help="Decimal places to keep when writing averaged percentage values",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging while discovering and aggregating CSV files",
    )
    parser.add_argument(
        "--inspect-cell",
        nargs=2,
        metavar=("COLUMN", "ROW"),
        help=(
            "Print the percentage value for a spreadsheet-style cell in each file, "
            "for example --inspect-cell E 6"
        ),
    )
    return parser.parse_args()


def find_matching_csvs(run_dir: Path, filename: str) -> List[Path]:
    """Return all matching CSV files located directly under an sb_count directory."""
    return sorted(
        path
        for path in run_dir.rglob(filename)
        if path.is_file() and path.parent.name == "sb_count"
    )


def find_seed_dirs(run_dir: Path) -> List[Path]:
    """Return direct child directories named seed_* in sorted order."""
    return sorted(
        child
        for child in run_dir.iterdir()
        if child.is_dir() and child.name.startswith("seed_")
    )


def read_csv_matrix(csv_path: Path) -> List[List[str]]:
    """Read a CSV file and pad rows so every row has the same number of columns."""
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
    """Convert a data cell to float, treating blank cells as zero."""
    text = cell.strip()
    if not text:
        return 0.0

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"expected a numeric data cell, found {cell!r}") from exc


def validate_same_layout(
    template_rows: Sequence[Sequence[str]],
    candidate_rows: Sequence[Sequence[str]],
    candidate_path: Path,
) -> None:
    """Ensure all files use the same shape and header layout before averaging."""
    if len(template_rows) != len(candidate_rows):
        raise ValueError(
            f"{candidate_path} has {len(candidate_rows)} rows, expected "
            f"{len(template_rows)}"
        )

    template_width = len(template_rows[0])
    candidate_width = len(candidate_rows[0])
    if template_width != candidate_width:
        raise ValueError(
            f"{candidate_path} has {candidate_width} columns, expected "
            f"{template_width}"
        )

    if list(template_rows[:HEADER_ROWS]) != list(candidate_rows[:HEADER_ROWS]):
        raise ValueError(
            f"{candidate_path} does not match the first {HEADER_ROWS} header rows "
            "of the template CSV"
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


def normalize_body(
    rows: Sequence[Sequence[str]],
    csv_path: Path,
) -> Tuple[List[List[float]], float]:
    """Convert every numeric body cell to percentage of total used connections."""
    totals = [
        [
            cell_to_float(rows[row_index][col_index])
            for col_index in range(HEADER_COLS, len(rows[row_index]))
        ]
        for row_index in range(HEADER_ROWS, len(rows))
    ]

    total_used_connections = sum(sum(row) for row in totals)
    if total_used_connections <= 0.0:
        raise ValueError(f"{csv_path} contains no used connections to normalize")

    percentage_body = [
        [(value / total_used_connections) * PERCENT_SCALE for value in row_values]
        for row_values in totals
    ]
    return percentage_body, total_used_connections


def build_output_rows(
    template_rows: Sequence[Sequence[str]],
    averaged_body: Sequence[Sequence[float]],
    precision: int,
) -> List[List[str]]:
    """Create the final CSV content while preserving the original headers."""
    output_rows = [list(row) for row in template_rows]

    for body_row_index, row_values in enumerate(averaged_body, start=HEADER_ROWS):
        for body_col_offset, value in enumerate(row_values, start=HEADER_COLS):
            output_rows[body_row_index][body_col_offset] = format_float(
                value,
                precision,
            )

    return output_rows


def extract_body_values(rows: Sequence[Sequence[str]]) -> List[List[float]]:
    """Extract the numeric data body from a CSV matrix."""
    return [
        [
            cell_to_float(rows[row_index][col_index])
            for col_index in range(HEADER_COLS, len(rows[row_index]))
        ]
        for row_index in range(HEADER_ROWS, len(rows))
    ]


def format_float(value: float, precision: int) -> str:
    """Format floats compactly while keeping a consistent precision limit."""
    text = f"{value:.{precision}f}".rstrip("0").rstrip(".")
    return text if text else "0"


@dataclass(frozen=True)
class TapUsageSummary:
    """Summary percentages for one source tap in an aggregate CSV."""

    tap: str
    overall_wire_to_wire_percent: float
    incremental_wire_percent: float
    decremental_wire_percent: float


def spreadsheet_column_to_index(column_label: str) -> int:
    """Convert spreadsheet column letters such as A or AA to a zero-based index."""
    normalized = column_label.strip().upper()
    if not normalized or not normalized.isalpha():
        raise ValueError(
            f"invalid column label {column_label!r}; expected letters like A, B, or AA"
        )

    index = 0
    for char in normalized:
        index = index * 26 + (ord(char) - ord("A") + 1)

    return index - 1


def parse_inspect_cell(
    inspect_cell_args: Sequence[str] | None,
) -> Tuple[int, int] | None:
    """Parse the optional spreadsheet-style cell coordinate from the CLI."""
    if inspect_cell_args is None:
        return None

    column_label, row_text = inspect_cell_args
    try:
        row_number = int(row_text)
    except ValueError as exc:
        raise ValueError(
            f"invalid row number {row_text!r}; expected a positive integer"
        ) from exc

    if row_number <= 0:
        raise ValueError(
            f"invalid row number {row_text!r}; expected a positive integer"
        )

    return spreadsheet_column_to_index(column_label), row_number - 1


def validate_inspect_cell(
    inspect_cell: Tuple[int, int],
    template_rows: Sequence[Sequence[str]],
) -> None:
    """Ensure the requested cell exists and is inside the numeric data body."""
    inspect_col_index, inspect_row_index = inspect_cell
    row_count = len(template_rows)
    col_count = len(template_rows[0])

    if inspect_row_index >= row_count:
        raise ValueError(
            f"requested row {inspect_row_index + 1} is outside the CSV height of {row_count}"
        )

    if inspect_col_index >= col_count:
        raise ValueError(
            "requested column is outside the CSV width of "
            f"{format_spreadsheet_cell(col_count - 1, inspect_row_index)[0]}"
        )

    if inspect_row_index < HEADER_ROWS or inspect_col_index < HEADER_COLS:
        raise ValueError(
            "requested cell is in the preserved header area; please choose a data "
            f"cell at row >= {HEADER_ROWS + 1} and column >= "
            f"{index_to_spreadsheet_column(HEADER_COLS)}"
        )


def index_to_spreadsheet_column(column_index: int) -> str:
    """Convert a zero-based column index to spreadsheet letters."""
    if column_index < 0:
        raise ValueError("column index must be non-negative")

    letters: List[str] = []
    value = column_index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("A") + remainder))

    return "".join(reversed(letters))


def format_spreadsheet_cell(column_index: int, row_index: int) -> Tuple[str, int]:
    """Return a spreadsheet-style cell address as column letters and 1-based row."""
    return index_to_spreadsheet_column(column_index), row_index + 1


def configure_logging(debug_enabled: bool) -> None:
    """Configure CLI logging for optional debug output."""
    logging.basicConfig(
        level=logging.DEBUG if debug_enabled else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def describe_circuit(csv_path: Path, run_dir: Path) -> str:
    """Return a friendly circuit label for debug output."""
    try:
        relative_path = csv_path.relative_to(run_dir)
    except ValueError:
        return str(csv_path)

    circuit_name = relative_path.parts[0] if relative_path.parts else csv_path.stem
    return f"{circuit_name} ({relative_path})"


def is_wire_side(side_label: str) -> bool:
    """Return True when the side label belongs to a wire, not an IPIN/OPIN."""
    return side_label in WIRE_SIDES


def is_incremental_wire_side(side_label: str) -> bool:
    """Return True for source wire sides considered incremental."""
    return side_label in INCREMENTAL_WIRE_SIDES


def is_decremental_wire_side(side_label: str) -> bool:
    """Return True for source wire sides considered decremental."""
    return side_label in DECREMENTAL_WIRE_SIDES


def tap_sort_key(tap_label: str) -> Tuple[int, float | str]:
    """Sort numeric tap labels numerically while keeping a string fallback."""
    try:
        return 0, float(tap_label)
    except ValueError:
        return 1, tap_label


def compute_tap_usage_summaries(
    aggregate_rows: Sequence[Sequence[str]],
) -> List[TapUsageSummary]:
    """Summarize source-tap utilization from an aggregate percentage matrix.

    The analysis operates only on wire-to-wire connections:
    - Rows are included only when their side label in column 1 is a wire side.
    - Columns are included only when their side label in header row 1 is a wire side.
    - Incremental and decremental usage are classified from the source-wire side
      in column 1, following the user's convention.
    """
    overall_by_tap: DefaultDict[str, float] = defaultdict(float)
    incremental_by_tap: DefaultDict[str, float] = defaultdict(float)
    decremental_by_tap: DefaultDict[str, float] = defaultdict(float)
    overall_total = 0.0
    incremental_total = 0.0
    decremental_total = 0.0

    # Destination columns are filtered so the analysis stays wire-to-wire only.
    wire_column_indices = [
        column_index
        for column_index in range(HEADER_COLS, len(aggregate_rows[0]))
        if is_wire_side(aggregate_rows[0][column_index])
    ]

    for row in aggregate_rows[HEADER_ROWS:]:
        row_side = row[0].strip()
        tap_label = row[3].strip()
        if not is_wire_side(row_side) or not tap_label:
            continue

        # Each row belongs to one source tap, so we accumulate that row's
        # wire-to-wire usage into the matching tap bucket. Incremental versus
        # decremental is determined only by the source side in column 1.
        overall_value = sum(cell_to_float(row[column_index]) for column_index in wire_column_indices)

        overall_by_tap[tap_label] += overall_value
        overall_total += overall_value
        if is_incremental_wire_side(row_side):
            incremental_by_tap[tap_label] += overall_value
            incremental_total += overall_value
        elif is_decremental_wire_side(row_side):
            decremental_by_tap[tap_label] += overall_value
            decremental_total += overall_value

    if overall_total <= 0.0:
        raise ValueError("aggregate CSV contains no wire-to-wire data for tap analysis")

    tap_labels = sorted(
        set(overall_by_tap) | set(incremental_by_tap) | set(decremental_by_tap),
        key=tap_sort_key,
    )
    summaries: List[TapUsageSummary] = []
    for tap_label in tap_labels:
        # Re-normalize within each filtered population so the reported tap
        # percentages sum to 100 for overall wires, incremental wires, and
        # decremental wires.
        overall_percent = (overall_by_tap[tap_label] / overall_total) * PERCENT_SCALE
        incremental_percent = 0.0
        decremental_percent = 0.0
        if incremental_total > 0.0:
            incremental_percent = (
                incremental_by_tap[tap_label] / incremental_total
            ) * PERCENT_SCALE
        if decremental_total > 0.0:
            decremental_percent = (
                decremental_by_tap[tap_label] / decremental_total
            ) * PERCENT_SCALE

        summaries.append(
            TapUsageSummary(
                tap=tap_label,
                overall_wire_to_wire_percent=overall_percent,
                incremental_wire_percent=incremental_percent,
                decremental_wire_percent=decremental_percent,
            )
        )

    return summaries


def build_tap_usage_rows(
    summaries: Sequence[TapUsageSummary],
    precision: int,
) -> List[List[str]]:
    """Build CSV rows for the tap-usage summary report."""
    rows = [
        [
            "tap",
            "overall_wire_to_wire_utilization_percent",
            "incremental_wire_utilization_percent",
            "decremental_wire_utilization_percent",
        ]
    ]

    for summary in summaries:
        rows.append(
            [
                summary.tap,
                format_float(summary.overall_wire_to_wire_percent, precision),
                format_float(summary.incremental_wire_percent, precision),
                format_float(summary.decremental_wire_percent, precision),
            ]
        )

    return rows


def tap_usage_output_path(aggregate_output_path: Path) -> Path:
    """Return the output path for the tap-usage summary next to an aggregate CSV."""
    return aggregate_output_path.with_name(f"tap_usage_{aggregate_output_path.name}")


def write_tap_usage_summary(
    aggregate_rows: Sequence[Sequence[str]],
    aggregate_output_path: Path,
    precision: int,
) -> Path:
    """Analyze one aggregate CSV matrix and write its tap-usage summary CSV."""
    summary_rows = build_tap_usage_rows(
        compute_tap_usage_summaries(aggregate_rows),
        precision,
    )
    output_path = tap_usage_output_path(aggregate_output_path)
    write_csv(summary_rows, output_path)
    return output_path


def aggregate_switch_block_csvs(
    csv_paths: Sequence[Path],
    run_dir: Path,
    precision: int,
    inspect_cell: Tuple[int, int] | None,
) -> List[List[str]]:
    """Aggregate all percentage-based switch-box CSVs into one averaged matrix."""
    if not csv_paths:
        raise ValueError("no matching switch-box CSV files were found")

    template_rows = read_csv_matrix(csv_paths[0])
    if inspect_cell is not None:
        validate_inspect_cell(inspect_cell, template_rows)
    template_width = len(template_rows[0]) - HEADER_COLS
    template_height = len(template_rows) - HEADER_ROWS
    accumulated_body = [
        [0.0 for _ in range(template_width)]
        for _ in range(template_height)
    ]

    for csv_path in csv_paths:
        rows = read_csv_matrix(csv_path)
        validate_same_layout(template_rows, rows, csv_path)
        percentage_body, total_used_connections = normalize_body(rows, csv_path)
        logging.debug(
            "Circuit %s total used connections: %s",
            describe_circuit(csv_path, run_dir),
            format_float(total_used_connections, 0),
        )
        if inspect_cell is not None:
            inspect_col_index, inspect_row_index = inspect_cell
            body_row_index = inspect_row_index - HEADER_ROWS
            body_col_index = inspect_col_index - HEADER_COLS
            cell_percentage = percentage_body[body_row_index][body_col_index]
            cell_column, cell_row = format_spreadsheet_cell(
                inspect_col_index,
                inspect_row_index,
            )
            print(
                "Cell "
                f"{cell_column}{cell_row} for {describe_circuit(csv_path, run_dir)}: "
                f"{format_float(cell_percentage, precision)}%"
            )

        for row_index, row_values in enumerate(percentage_body):
            for col_index, value in enumerate(row_values):
                accumulated_body[row_index][col_index] += value

    file_count = len(csv_paths)
    averaged_body = [
        [value / file_count for value in row_values]
        for row_values in accumulated_body
    ]

    return build_output_rows(template_rows, averaged_body, precision)


def average_aggregate_rows(
    named_rows: Sequence[Tuple[str, Sequence[Sequence[str]]]],
    precision: int,
) -> List[List[str]]:
    """Average already-aggregated percentage CSV rows cell by cell."""
    if not named_rows:
        raise ValueError("no aggregate CSV rows were provided for averaging")

    _, template_rows = named_rows[0]
    template_width = len(template_rows[0]) - HEADER_COLS
    template_height = len(template_rows) - HEADER_ROWS
    accumulated_body = [
        [0.0 for _ in range(template_width)]
        for _ in range(template_height)
    ]

    for source_name, rows in named_rows:
        validate_same_layout(template_rows, rows, Path(source_name))
        body_values = extract_body_values(rows)
        for row_index, row_values in enumerate(body_values):
            for col_index, value in enumerate(row_values):
                accumulated_body[row_index][col_index] += value

    averaged_body = [
        [value / len(named_rows) for value in row_values]
        for row_values in accumulated_body
    ]
    return build_output_rows(template_rows, averaged_body, precision)


def write_csv(rows: Sequence[Sequence[str]], output_path: Path) -> None:
    """Write the aggregated CSV file to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def process_single_run_dir(
    run_dir: Path,
    pattern_name: str,
    output_dir: Path,
    precision: int,
    inspect_cell: Tuple[int, int] | None,
) -> Tuple[int, Path, Path]:
    """Aggregate one run directory and write a single output CSV."""
    matching_csvs = find_matching_csvs(run_dir, pattern_name)
    logging.debug(
        "Found %d matching '%s' files under %s",
        len(matching_csvs),
        pattern_name,
        run_dir,
    )
    if not matching_csvs:
        raise ValueError(
            "no matching files were found under sb_count directories for "
            f"{pattern_name!r} in {run_dir}"
        )

    output_path = output_dir / f"aggregate_{pattern_name}"
    aggregated_rows = aggregate_switch_block_csvs(
        matching_csvs,
        run_dir,
        precision,
        inspect_cell,
    )
    write_csv(aggregated_rows, output_path)
    tap_usage_path = write_tap_usage_summary(aggregated_rows, output_path, precision)
    return len(matching_csvs), output_path, tap_usage_path


def process_seed_runs(
    run_dir: Path,
    seed_dirs: Sequence[Path],
    pattern_name: str,
    output_dir: Path | None,
    precision: int,
    inspect_cell: Tuple[int, int] | None,
) -> Tuple[List[Tuple[Path, int, Path, Path]], Tuple[Path, Path] | None]:
    """Aggregate each seed directory and optionally build a run-level average."""
    seed_results: List[Tuple[Path, int, Path, Path]] = []
    seed_aggregate_rows: List[Tuple[str, Sequence[Sequence[str]]]] = []

    for seed_dir in seed_dirs:
        matching_csvs = find_matching_csvs(seed_dir, pattern_name)
        logging.debug(
            "Found %d matching '%s' files under seed %s",
            len(matching_csvs),
            pattern_name,
            seed_dir,
        )
        if not matching_csvs:
            logging.warning(
                "Skipping %s because it contains no '%s' files under sb_count directories",
                seed_dir,
                pattern_name,
            )
            continue

        seed_output_dir = seed_dir if output_dir is None else output_dir / seed_dir.name
        seed_output_path = seed_output_dir / f"aggregate_{pattern_name}"
        aggregated_rows = aggregate_switch_block_csvs(
            matching_csvs,
            seed_dir,
            precision,
            inspect_cell,
        )
        write_csv(aggregated_rows, seed_output_path)
        tap_usage_path = write_tap_usage_summary(
            aggregated_rows,
            seed_output_path,
            precision,
        )
        seed_results.append((seed_dir, len(matching_csvs), seed_output_path, tap_usage_path))
        seed_aggregate_rows.append((seed_dir.name, aggregated_rows))

    if not seed_results:
        raise ValueError(
            "no seed_* directories contained matching files under sb_count directories "
            f"for {pattern_name!r} in {run_dir}"
        )

    run_level_results: Tuple[Path, Path] | None = None
    if output_dir is None:
        run_level_output_path = run_dir / f"aggregate_{pattern_name}"
        run_level_rows = average_aggregate_rows(seed_aggregate_rows, precision)
        write_csv(run_level_rows, run_level_output_path)
        run_level_tap_usage_path = write_tap_usage_summary(
            run_level_rows,
            run_level_output_path,
            precision,
        )
        run_level_results = (run_level_output_path, run_level_tap_usage_path)

    return seed_results, run_level_results


def main() -> int:
    """Program entry point."""
    args = parse_args()
    configure_logging(args.debug)
    try:
        inspect_cell = parse_inspect_cell(args.inspect_cell)
        run_dir = args.run_dir.resolve()
        output_dir = args.output_dir.resolve() if args.output_dir else None
        pattern_name = Path(args.switch_block_pattern).name

        if not run_dir.is_dir():
            print(f"error: run directory does not exist: {run_dir}", file=sys.stderr)
            return 1

        seed_dirs = find_seed_dirs(run_dir)
        if seed_dirs:
            seed_results, run_level_results = process_seed_runs(
                run_dir,
                seed_dirs,
                pattern_name,
                output_dir,
                args.precision,
                inspect_cell,
            )
            for seed_dir, file_count, seed_output_path, tap_usage_path in seed_results:
                print(f"Processed {file_count} files in {seed_dir.name}.")
                print(f"Wrote aggregate CSV to: {seed_output_path}")
                print(f"Wrote tap-usage CSV to: {tap_usage_path}")

            if run_level_results is not None:
                run_level_output_path, run_level_tap_usage_path = run_level_results
                print(f"Averaged {len(seed_results)} seed aggregate files.")
                print(f"Wrote aggregate CSV to: {run_level_output_path}")
                print(f"Wrote tap-usage CSV to: {run_level_tap_usage_path}")
        else:
            effective_output_dir = output_dir or run_dir
            file_count, output_path, tap_usage_path = process_single_run_dir(
                run_dir,
                pattern_name,
                effective_output_dir,
                args.precision,
                inspect_cell,
            )
            print(f"Processed {file_count} files.")
            print(f"Wrote aggregate CSV to: {output_path}")
            print(f"Wrote tap-usage CSV to: {tap_usage_path}")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
