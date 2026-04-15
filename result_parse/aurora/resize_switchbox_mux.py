#!/usr/bin/env python3
"""Resize wire-to-wire muxes in a switch-box pattern CSV.

The script changes only wire-to-wire connections:
- wire rows are rows whose first column is Left/Right/Top/Bottom
- wire columns are columns whose first header row is Left/Right/Top/Bottom

For every wire sink column, the final fan-in is forced to the requested mux size.
When adding new switches, the script uses the ceiling of the average existing
wire-to-wire delay value from the input pattern. While adding or removing
switches, it tries to keep wire-row fanout balanced across source rows. Newly
added wire-to-wire switches are only allowed between different sides.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


HEADER_ROWS = 5
HEADER_COLS = 4
WIRE_SIDES = {"Left", "Right", "Top", "Bottom"}


@dataclass(frozen=True)
class MatrixIndexSet:
    """Indices for wire rows and wire columns in the switch-box matrix."""

    wire_rows: List[int]
    wire_cols: List[int]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for mux resizing."""
    parser = argparse.ArgumentParser(
        description=(
            "Resize wire-to-wire sink muxes in a switch-box pattern CSV by adding "
            "or removing switches while keeping source-row fanout balanced."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "target_mux_size",
        type=int,
        help="Requested wire-to-wire fan-in for every wire sink column",
    )
    parser.add_argument(
        "pattern_csv",
        type=Path,
        help="Path to the switch-box pattern CSV to modify",
    )
    parser.add_argument(
        "-o",
        "--output-csv",
        type=Path,
        default=None,
        help="Where to write the modified pattern CSV",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed used to break ties during rewiring",
    )
    parser.add_argument(
        "--delay-precision",
        type=int,
        default=6,
        help="Decimal places to keep when printing the average delay summary",
    )
    return parser.parse_args()


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


def write_csv(rows: Sequence[Sequence[str]], output_path: Path) -> None:
    """Write a CSV matrix to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def is_wire_side(label: str) -> bool:
    """Return True when a row or column label describes a wire side."""
    return label.strip() in WIRE_SIDES


def get_wire_row_side(rows: Sequence[Sequence[str]], row_index: int) -> str:
    """Return the wire side label for a source row."""
    return rows[row_index][0].strip()


def get_wire_col_side(rows: Sequence[Sequence[str]], col_index: int) -> str:
    """Return the wire side label for a sink column."""
    return rows[0][col_index].strip()


def is_cross_side_wire_connection(
    rows: Sequence[Sequence[str]],
    row_index: int,
    col_index: int,
) -> bool:
    """Return True when a wire-to-wire connection spans different sides."""
    return get_wire_row_side(rows, row_index) != get_wire_col_side(rows, col_index)


def find_wire_indices(rows: Sequence[Sequence[str]]) -> MatrixIndexSet:
    """Locate all wire rows and wire columns in the matrix."""
    wire_rows = [
        row_index
        for row_index in range(HEADER_ROWS, len(rows))
        if is_wire_side(rows[row_index][0])
    ]
    wire_cols = [
        col_index
        for col_index in range(HEADER_COLS, len(rows[0]))
        if is_wire_side(rows[0][col_index])
    ]

    if not wire_rows or not wire_cols:
        raise ValueError("pattern CSV contains no wire-to-wire rows or columns")

    return MatrixIndexSet(wire_rows=wire_rows, wire_cols=wire_cols)


def cell_to_float(cell: str) -> float:
    """Convert a numeric cell to float, treating blanks as absent values."""
    text = cell.strip()
    if not text:
        raise ValueError("cannot convert an empty cell to float")
    return float(text)


def format_numeric(value: float, precision: int) -> str:
    """Format numbers compactly for CSV output."""
    if float(value).is_integer():
        return str(int(round(value)))

    text = f"{value:.{precision}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def compute_average_wire_delay(
    rows: Sequence[Sequence[str]],
    index_set: MatrixIndexSet,
) -> float:
    """Return the average delay across existing wire-to-wire switches."""
    delays = [
        cell_to_float(rows[row_index][col_index])
        for row_index in index_set.wire_rows
        for col_index in index_set.wire_cols
        if rows[row_index][col_index].strip()
    ]

    if not delays:
        raise ValueError("pattern CSV contains no existing wire-to-wire delay values")

    return statistics.mean(delays)


def build_adjacency(
    rows: Sequence[Sequence[str]],
    index_set: MatrixIndexSet,
) -> Tuple[Dict[Tuple[int, int], bool], Dict[int, int], Dict[int, int]]:
    """Build edge presence plus row/column degree tables for wire-to-wire cells."""
    adjacency: Dict[Tuple[int, int], bool] = {}
    row_degrees = {row_index: 0 for row_index in index_set.wire_rows}
    col_degrees = {col_index: 0 for col_index in index_set.wire_cols}

    for row_index in index_set.wire_rows:
        for col_index in index_set.wire_cols:
            present = bool(rows[row_index][col_index].strip())
            adjacency[(row_index, col_index)] = present
            if present:
                row_degrees[row_index] += 1
                col_degrees[col_index] += 1

    return adjacency, row_degrees, col_degrees


def choose_rows_for_extra_fanout(
    row_degrees: Dict[int, int],
    extra_count: int,
    rng: random.Random,
) -> List[int]:
    """Choose which rows receive the +1 target when total fanout is not divisible."""
    grouped_rows: Dict[int, List[int]] = {}
    for row_index, degree in row_degrees.items():
        grouped_rows.setdefault(degree, []).append(row_index)

    chosen_rows: List[int] = []
    for degree in sorted(grouped_rows, reverse=True):
        rows_at_degree = list(grouped_rows[degree])
        rng.shuffle(rows_at_degree)
        for row_index in rows_at_degree:
            if len(chosen_rows) >= extra_count:
                return chosen_rows
            chosen_rows.append(row_index)

    return chosen_rows


def build_desired_row_degrees(
    row_degrees: Dict[int, int],
    total_target_edges: int,
    rng: random.Random,
) -> Dict[int, int]:
    """Assign balanced target fanout values to rows.

    The final row fanout is as even as possible: every row gets either floor(avg)
    or ceil(avg), with tie-breaking biased toward rows that already have larger
    fanout so the change set stays smaller.
    """
    row_count = len(row_degrees)
    base_degree = total_target_edges // row_count
    extra_count = total_target_edges % row_count
    desired_degrees = {row_index: base_degree for row_index in row_degrees}

    for row_index in choose_rows_for_extra_fanout(row_degrees, extra_count, rng):
        desired_degrees[row_index] += 1

    return desired_degrees


def choose_row_for_addition(
    candidates: Sequence[int],
    row_degrees: Dict[int, int],
    desired_row_degrees: Dict[int, int],
    rng: random.Random,
) -> int:
    """Choose an addition candidate that best improves row fanout balance."""
    deficits = {
        row_index: desired_row_degrees[row_index] - row_degrees[row_index]
        for row_index in candidates
    }
    max_deficit = max(deficits.values())
    if max_deficit > 0:
        preferred = [row_index for row_index in candidates if deficits[row_index] == max_deficit]
    else:
        min_degree = min(row_degrees[row_index] for row_index in candidates)
        preferred = [row_index for row_index in candidates if row_degrees[row_index] == min_degree]

    return rng.choice(preferred)


def choose_row_for_removal(
    candidates: Sequence[int],
    row_degrees: Dict[int, int],
    desired_row_degrees: Dict[int, int],
    rng: random.Random,
) -> int:
    """Choose a removal candidate that best improves row fanout balance."""
    surpluses = {
        row_index: row_degrees[row_index] - desired_row_degrees[row_index]
        for row_index in candidates
    }
    max_surplus = max(surpluses.values())
    if max_surplus > 0:
        preferred = [row_index for row_index in candidates if surpluses[row_index] == max_surplus]
    else:
        max_degree = max(row_degrees[row_index] for row_index in candidates)
        preferred = [row_index for row_index in candidates if row_degrees[row_index] == max_degree]

    return rng.choice(preferred)


def add_switches(
    rows: List[List[str]],
    index_set: MatrixIndexSet,
    adjacency: Dict[Tuple[int, int], bool],
    row_degrees: Dict[int, int],
    col_degrees: Dict[int, int],
    desired_row_degrees: Dict[int, int],
    target_mux_size: int,
    added_delay: str,
    rng: random.Random,
) -> None:
    """Add wire-to-wire switches until every sink reaches the target mux size."""
    pending_cols = [col_index for col_index in index_set.wire_cols if col_degrees[col_index] < target_mux_size]
    rng.shuffle(pending_cols)

    while pending_cols:
        progress_made = False
        next_pending_cols: List[int] = []

        for col_index in pending_cols:
            while col_degrees[col_index] < target_mux_size:
                candidates = [
                    row_index
                    for row_index in index_set.wire_rows
                    if (
                        not adjacency[(row_index, col_index)]
                        and is_cross_side_wire_connection(rows, row_index, col_index)
                    )
                ]
                if not candidates:
                    raise ValueError(
                        "cannot reach target mux size "
                        f"{target_mux_size} for wire column {col_index + 1} "
                        "without adding a same-side wire connection"
                    )

                row_index = choose_row_for_addition(
                    candidates,
                    row_degrees,
                    desired_row_degrees,
                    rng,
                )
                adjacency[(row_index, col_index)] = True
                row_degrees[row_index] += 1
                col_degrees[col_index] += 1
                rows[row_index][col_index] = added_delay
                progress_made = True

            if col_degrees[col_index] < target_mux_size:
                next_pending_cols.append(col_index)

        if not progress_made and next_pending_cols:
            raise ValueError("failed to add enough switches to reach the target mux size")

        pending_cols = next_pending_cols


def remove_switches(
    rows: List[List[str]],
    index_set: MatrixIndexSet,
    adjacency: Dict[Tuple[int, int], bool],
    row_degrees: Dict[int, int],
    col_degrees: Dict[int, int],
    desired_row_degrees: Dict[int, int],
    target_mux_size: int,
    rng: random.Random,
) -> None:
    """Remove wire-to-wire switches until every sink reaches the target mux size."""
    pending_cols = [col_index for col_index in index_set.wire_cols if col_degrees[col_index] > target_mux_size]
    rng.shuffle(pending_cols)

    while pending_cols:
        progress_made = False
        next_pending_cols: List[int] = []

        for col_index in pending_cols:
            while col_degrees[col_index] > target_mux_size:
                candidates = [
                    row_index
                    for row_index in index_set.wire_rows
                    if adjacency[(row_index, col_index)]
                ]
                if not candidates:
                    raise ValueError(
                        f"wire column {col_index + 1} has no removable switches but still exceeds the target"
                    )

                row_index = choose_row_for_removal(
                    candidates,
                    row_degrees,
                    desired_row_degrees,
                    rng,
                )
                adjacency[(row_index, col_index)] = False
                row_degrees[row_index] -= 1
                col_degrees[col_index] -= 1
                rows[row_index][col_index] = ""
                progress_made = True

            if col_degrees[col_index] > target_mux_size:
                next_pending_cols.append(col_index)

        if not progress_made and next_pending_cols:
            raise ValueError("failed to remove enough switches to reach the target mux size")

        pending_cols = next_pending_cols


def verify_target_mux_size(
    col_degrees: Dict[int, int],
    target_mux_size: int,
) -> None:
    """Ensure every wire sink column now has the requested fan-in."""
    bad_columns = [
        col_index + 1
        for col_index, degree in col_degrees.items()
        if degree != target_mux_size
    ]
    if bad_columns:
        raise ValueError(
            "failed to enforce the requested wire-to-wire mux size for columns "
            f"{bad_columns}"
        )


def summarize_row_fanout(row_degrees: Dict[int, int]) -> str:
    """Return a compact summary string for row fanout statistics."""
    degree_values = list(row_degrees.values())
    return (
        f"min={min(degree_values)} max={max(degree_values)} "
        f"avg={statistics.mean(degree_values):.4f}"
    )


def build_default_output_path(pattern_csv: Path, target_mux_size: int) -> Path:
    """Choose the default output filename beside the input CSV."""
    return pattern_csv.with_name(
        f"{pattern_csv.stem}_wire_mux_{target_mux_size}{pattern_csv.suffix}"
    )


def main() -> int:
    """Program entry point."""
    args = parse_args()
    rng = random.Random(args.seed)

    try:
        if args.target_mux_size <= 0:
            raise ValueError("target_mux_size must be a positive integer")

        pattern_csv = args.pattern_csv.resolve()
        if not pattern_csv.is_file():
            print(f"error: pattern CSV does not exist: {pattern_csv}", file=sys.stderr)
            return 1

        rows = read_csv_matrix(pattern_csv)
        index_set = find_wire_indices(rows)
        if args.target_mux_size > len(index_set.wire_rows):
            raise ValueError(
                "target mux size exceeds the number of available wire source rows"
            )

        average_wire_delay = compute_average_wire_delay(rows, index_set)
        added_wire_delay = str(math.ceil(average_wire_delay))
        adjacency, row_degrees, col_degrees = build_adjacency(rows, index_set)
        original_row_fanout_summary = summarize_row_fanout(row_degrees)
        total_target_edges = args.target_mux_size * len(index_set.wire_cols)
        desired_row_degrees = build_desired_row_degrees(
            row_degrees,
            total_target_edges,
            rng,
        )

        current_col_degrees = set(col_degrees.values())
        output_csv = (
            args.output_csv.resolve()
            if args.output_csv is not None
            else build_default_output_path(pattern_csv, args.target_mux_size)
        )

        if max(col_degrees.values()) < args.target_mux_size:
            add_switches(
                rows,
                index_set,
                adjacency,
                row_degrees,
                col_degrees,
                desired_row_degrees,
                args.target_mux_size,
                added_wire_delay,
                rng,
            )
        elif min(col_degrees.values()) > args.target_mux_size:
            remove_switches(
                rows,
                index_set,
                adjacency,
                row_degrees,
                col_degrees,
                desired_row_degrees,
                args.target_mux_size,
                rng,
            )
        else:
            # Mixed-degree inputs are handled in both directions to force all
            # wire sink columns to the requested common mux size.
            remove_switches(
                rows,
                index_set,
                adjacency,
                row_degrees,
                col_degrees,
                desired_row_degrees,
                args.target_mux_size,
                rng,
            )
            add_switches(
                rows,
                index_set,
                adjacency,
                row_degrees,
                col_degrees,
                desired_row_degrees,
                args.target_mux_size,
                added_wire_delay,
                rng,
            )

        verify_target_mux_size(col_degrees, args.target_mux_size)
        write_csv(rows, output_csv)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Input pattern: {pattern_csv}")
    print(f"Output pattern: {output_csv}")
    print(f"Original wire-to-wire mux sizes: {sorted(current_col_degrees)}")
    print(f"Target wire-to-wire mux size: {args.target_mux_size}")
    print(
        "Average wire-to-wire delay before ceiling: "
        f"{format_numeric(average_wire_delay, args.delay_precision)}"
    )
    print(
        "Delay used for added switches (ceiling): "
        f"{added_wire_delay}"
    )
    print(f"Original row fanout summary: {original_row_fanout_summary}")
    print(f"Final row fanout summary: {summarize_row_fanout(row_degrees)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
