#!/usr/bin/env python3
"""
Script to modify IPIN column connections in switchbox CSV files.

For each data row:
- Reduce IPIN connections to exactly 2 (randomly selected)
- If a row has no IPIN connections, add 2 at random locations
- Use column averages for new values
- Ensure no IPIN column is left empty
- Maintain the same total number of connections per column

Directional constraints:
- I00 and I01 columns can only connect to Left and Right rows
- I02 and I03 columns can only connect to Top and Bottom rows
- IC0 columns can connect to any row type
"""

import csv
import random
import argparse
import re
from collections import defaultdict
from pathlib import Path


def read_csv(filepath):
    """Read CSV file and return rows as list of lists."""
    with open(filepath, 'r', newline='') as f:
        reader = csv.reader(f)
        return [row for row in reader]


def write_csv(filepath, rows):
    """Write rows to CSV file."""
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def find_ipin_columns(header_row):
    """Find the indices of IPIN columns from the header row."""
    ipin_indices = []
    for i, cell in enumerate(header_row):
        if cell == 'IPIN':
            ipin_indices.append(i)
    return ipin_indices


def classify_ipin_columns(rows, ipin_indices, pin_name_row=4):
    """
    Classify IPIN columns by their type based on pin names.
    Returns dict: col_idx -> 'I00', 'I01', 'I02', 'I03', 'IC0', or 'other'
    """
    column_types = {}
    pin_row = rows[pin_name_row]

    for col_idx in ipin_indices:
        if col_idx < len(pin_row):
            pin_name = pin_row[col_idx]
            # Parse pin name like "clb.I00[0]", "clb.I01[5]", "clb.IC0[2]"
            match = re.match(r'clb\.(I\d{2}|IC\d)\[', pin_name)
            if match:
                column_types[col_idx] = match.group(1)
            else:
                column_types[col_idx] = 'other'
        else:
            column_types[col_idx] = 'other'

    return column_types


def get_row_direction(row):
    """Get the direction (Left, Right, Top, Bottom) from a data row."""
    if len(row) > 0:
        return row[0].strip()
    return ''


def get_allowed_columns_for_direction(direction, ipin_indices, column_types):
    """
    Get the list of IPIN column indices allowed for a given row direction.
    - Left/Right rows -> I00, I01, IC0
    - Top/Bottom rows -> I02, I03, IC0
    """
    allowed = []
    for col_idx in ipin_indices:
        col_type = column_types.get(col_idx, 'other')

        if direction in ('Left', 'Right'):
            if col_type in ('I00', 'I01', 'IC0'):
                allowed.append(col_idx)
        elif direction in ('Top', 'Bottom'):
            if col_type in ('I02', 'I03', 'IC0'):
                allowed.append(col_idx)
        else:
            # Unknown direction, allow all
            allowed.append(col_idx)

    return allowed


def get_column_averages(rows, ipin_indices, header_rows=5):
    """Calculate the average value for each IPIN column (excluding empty cells)."""
    column_sums = defaultdict(float)
    column_counts = defaultdict(int)

    for row_idx in range(header_rows, len(rows)):
        row = rows[row_idx]
        for col_idx in ipin_indices:
            if col_idx < len(row) and row[col_idx].strip():
                try:
                    val = float(row[col_idx])
                    column_sums[col_idx] += val
                    column_counts[col_idx] += 1
                except ValueError:
                    pass

    averages = {}
    for col_idx in ipin_indices:
        if column_counts[col_idx] > 0:
            averages[col_idx] = column_sums[col_idx] / column_counts[col_idx]
        else:
            # If column has no values, use overall average
            total_sum = sum(column_sums.values())
            total_count = sum(column_counts.values())
            averages[col_idx] = total_sum / total_count if total_count > 0 else 250

    return averages


def get_column_connection_counts(rows, ipin_indices, header_rows=5):
    """Count how many connections each IPIN column currently has."""
    counts = defaultdict(int)
    for row_idx in range(header_rows, len(rows)):
        row = rows[row_idx]
        for col_idx in ipin_indices:
            if col_idx < len(row) and row[col_idx].strip():
                try:
                    float(row[col_idx])
                    counts[col_idx] += 1
                except ValueError:
                    pass
    return counts


def redistribute_connections(rows, ipin_indices, column_types, header_rows=5):
    """
    Redistribute IPIN connections so that:
    1. Each row has exactly 2 connections
    2. No column is empty
    3. Each column maintains the same total number of connections
    4. Directional constraints are respected:
       - Left/Right rows -> I00, I01, IC0 columns only
       - Top/Bottom rows -> I02, I03, IC0 columns only
    """
    num_data_rows = len(rows) - header_rows

    # Get column averages for filling values
    column_averages = get_column_averages(rows, ipin_indices, header_rows)

    # Separate rows by direction
    left_right_rows = []
    top_bottom_rows = []

    for row_idx in range(header_rows, len(rows)):
        direction = get_row_direction(rows[row_idx])
        if direction in ('Left', 'Right'):
            left_right_rows.append(row_idx)
        elif direction in ('Top', 'Bottom'):
            top_bottom_rows.append(row_idx)

    # Separate columns by allowed directions
    i00_i01_cols = [c for c in ipin_indices if column_types.get(c) in ('I00', 'I01')]
    i02_i03_cols = [c for c in ipin_indices if column_types.get(c) in ('I02', 'I03')]
    ic0_cols = [c for c in ipin_indices if column_types.get(c) == 'IC0']

    print(f"Number of data rows: {num_data_rows}")
    print(f"  Left/Right rows: {len(left_right_rows)}")
    print(f"  Top/Bottom rows: {len(top_bottom_rows)}")
    print(f"Number of IPIN columns: {len(ipin_indices)}")
    print(f"  I00/I01 columns (for Left/Right): {len(i00_i01_cols)}")
    print(f"  I02/I03 columns (for Top/Bottom): {len(i02_i03_cols)}")
    print(f"  IC0 columns (for any): {len(ic0_cols)}")

    # Get current column connection counts
    current_counts = get_column_connection_counts(rows, ipin_indices, header_rows)

    # Print original stats before modification
    print(f"\nOriginal stats (before modification):")
    orig_i0x_counts = [current_counts.get(c, 0) for c in i00_i01_cols + i02_i03_cols]
    orig_ic0_counts = [current_counts.get(c, 0) for c in ic0_cols]
    print(f"  I0x columns:")
    if orig_i0x_counts:
        print(f"    Connection counts: min={min(orig_i0x_counts)}, max={max(orig_i0x_counts)}, total={sum(orig_i0x_counts)}")
    print(f"  IC0 columns:")
    if orig_ic0_counts:
        print(f"    Connection counts: min={min(orig_ic0_counts)}, max={max(orig_ic0_counts)}, total={sum(orig_ic0_counts)}")
    print(f"  Total IPIN connections: {sum(current_counts.values())}")
    print(f"  Target I0x connections (2 per row): {2 * (len(left_right_rows) + len(top_bottom_rows))}")

    # Calculate target counts per column (scaled to new total)
    current_total = sum(current_counts.values())
    target_total = 2 * num_data_rows

    # We need to distribute connections respecting directional constraints
    # Left/Right rows need 2 connections each from I00, I01, IC0
    # Top/Bottom rows need 2 connections each from I02, I03, IC0

    lr_connections_needed = 2 * len(left_right_rows)
    tb_connections_needed = 2 * len(top_bottom_rows)

    # Columns available for Left/Right: I00, I01 only (IC0 unchanged)
    lr_cols = i00_i01_cols
    # Columns available for Top/Bottom: I02, I03 only (IC0 unchanged)
    tb_cols = i02_i03_cols

    def distribute_for_group(row_indices, allowed_cols, column_averages):
        """
        Distribute 2 connections per row among allowed columns.
        Uses a balanced greedy algorithm to minimize variation in column counts.
        """
        if not row_indices or not allowed_cols:
            return {}

        num_rows = len(row_indices)
        num_cols = len(allowed_cols)
        total_connections = 2 * num_rows

        # Calculate exact targets for each column
        base_per_col = total_connections // num_cols
        remainder = total_connections % num_cols

        # Assign targets - some columns get base+1, others get base
        target_per_col = {}
        shuffled_cols = list(allowed_cols)
        random.shuffle(shuffled_cols)  # Randomize which columns get the extra
        for i, col in enumerate(shuffled_cols):
            if i < remainder:
                target_per_col[col] = base_per_col + 1
            else:
                target_per_col[col] = base_per_col

        # Build assignment using balanced greedy approach
        assignment = {row_idx: [] for row_idx in row_indices}
        column_fill = {col: 0 for col in allowed_cols}

        # Shuffle rows for randomness
        shuffled_rows = list(row_indices)
        random.shuffle(shuffled_rows)

        def get_min_fill_column(exclude_cols):
            """Get the column with minimum fill count that's not in exclude list."""
            available = [(col, column_fill[col]) for col in allowed_cols
                        if col not in exclude_cols and column_fill[col] < target_per_col[col]]
            if not available:
                # All columns at target, pick any available with min fill
                available = [(col, column_fill[col]) for col in allowed_cols
                            if col not in exclude_cols]
            if not available:
                return None
            # Sort by fill count, then shuffle among ties for randomness
            min_fill = min(f for _, f in available)
            min_cols = [col for col, f in available if f == min_fill]
            return random.choice(min_cols)

        # Assign 2 connections per row, always picking columns with lowest fill
        for row_idx in shuffled_rows:
            for _ in range(2):
                col = get_min_fill_column(assignment[row_idx])
                if col is not None:
                    assignment[row_idx].append(col)
                    column_fill[col] += 1

        return assignment

    # Distribute for Left/Right rows
    lr_assignment = distribute_for_group(left_right_rows, lr_cols, column_averages)

    # Distribute for Top/Bottom rows
    tb_assignment = distribute_for_group(top_bottom_rows, tb_cols, column_averages)

    # Merge assignments
    assignment = {**lr_assignment, **tb_assignment}

    # Apply the assignment to the rows
    for row_idx in range(header_rows, len(rows)):
        row = rows[row_idx]

        # Extend row if necessary
        max_col = max(ipin_indices) + 1
        while len(row) < max_col:
            row.append('')

        # Clear only I00/I01/I02/I03 columns (preserve IC0)
        for col_idx in ipin_indices:
            if column_types.get(col_idx) in ('I00', 'I01', 'I02', 'I03'):
                row[col_idx] = ''

        # Set the assigned columns with column average values
        if row_idx in assignment:
            for col_idx in assignment[row_idx]:
                avg_value = column_averages.get(col_idx, 250)
                row[col_idx] = f"{avg_value:.0f}"

    # Verify results
    final_counts = get_column_connection_counts(rows, ipin_indices, header_rows)

    # Separate counts for I0x and IC0
    i0x_cols = i00_i01_cols + i02_i03_cols
    i0x_counts = [final_counts.get(c, 0) for c in i0x_cols]
    ic0_counts = [final_counts.get(c, 0) for c in ic0_cols]

    print(f"\nVerification:")

    # I0x columns stats
    empty_i0x = [c for c in i0x_cols if final_counts.get(c, 0) == 0]
    print(f"  I0x columns (modified):")
    print(f"    Empty: {len(empty_i0x)}")
    if i0x_counts:
        print(f"    Connection counts: min={min(i0x_counts)}, max={max(i0x_counts)}, total={sum(i0x_counts)}")

    # IC0 columns stats (unchanged)
    print(f"  IC0 columns (unchanged):")
    if ic0_counts:
        print(f"    Connection counts: min={min(ic0_counts)}, max={max(ic0_counts)}, total={sum(ic0_counts)}")

    print(f"  Total connections: {sum(final_counts.values())}")

    # Verify each Left/Right/Top/Bottom row has exactly 2 I0x connections
    rows_with_wrong_count = 0
    for row_idx in range(header_rows, len(rows)):
        direction = get_row_direction(rows[row_idx])
        if direction in ('Left', 'Right', 'Top', 'Bottom'):
            count = sum(1 for col_idx in i0x_cols if rows[row_idx][col_idx].strip())
            if count != 2:
                rows_with_wrong_count += 1
    print(f"  Left/Right/Top/Bottom rows without exactly 2 I0x connections: {rows_with_wrong_count}")

    # Verify directional constraints
    constraint_violations = 0
    for row_idx in range(header_rows, len(rows)):
        direction = get_row_direction(rows[row_idx])
        for col_idx in ipin_indices:
            if rows[row_idx][col_idx].strip():
                col_type = column_types.get(col_idx)
                if direction in ('Left', 'Right') and col_type in ('I02', 'I03'):
                    constraint_violations += 1
                elif direction in ('Top', 'Bottom') and col_type in ('I00', 'I01'):
                    constraint_violations += 1
    print(f"  Directional constraint violations: {constraint_violations}")

    return rows


def main():
    parser = argparse.ArgumentParser(
        description='Modify IPIN connections in switchbox CSV files'
    )
    parser.add_argument('input_csv', help='Input CSV file path')
    parser.add_argument('-o', '--output', help='Output CSV file path (default: input_modified.csv)')
    parser.add_argument('--seed', type=int, help='Random seed for reproducibility')
    parser.add_argument('--header-rows', type=int, default=5,
                        help='Number of header rows to skip (default: 5)')
    parser.add_argument('--pin-name-row', type=int, default=4,
                        help='Row index (0-based) containing pin names (default: 4)')

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    input_path = Path(args.input_csv)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_modified{input_path.suffix}"

    print(f"Reading: {input_path}")
    rows = read_csv(input_path)

    if len(rows) < args.header_rows + 1:
        print("Error: CSV file doesn't have enough rows")
        return 1

    # Find IPIN columns from the first header row
    ipin_indices = find_ipin_columns(rows[0])

    if not ipin_indices:
        print("Error: No IPIN columns found in the header row")
        return 1

    print(f"Found {len(ipin_indices)} IPIN columns (indices {min(ipin_indices)} to {max(ipin_indices)})")

    # Classify IPIN columns by type
    column_types = classify_ipin_columns(rows, ipin_indices, args.pin_name_row)
    type_counts = defaultdict(int)
    for col_type in column_types.values():
        type_counts[col_type] += 1
    print(f"Column types: {dict(type_counts)}")

    # Redistribute connections
    rows = redistribute_connections(rows, ipin_indices, column_types, args.header_rows)

    # Write output
    print(f"\nWriting: {output_path}")
    write_csv(output_path, rows)
    print("Done!")

    return 0


if __name__ == '__main__':
    exit(main())
