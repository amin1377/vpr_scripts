#!/usr/bin/env python3
"""
Script to modify I0X IPIN connections in switchbox CSV files.

The switchbox CSV is a connection matrix with two perspectives for IPIN fan-in:
  - IPIN COLUMNS in data rows: connections from wire "regular taps" to IPINs
  - IPIN ROWS at the bottom: connections from wire "tap zero" to IPINs

For each I0X pin, total fan-in = column connections + row connections.
Both perspectives are redistributed by this script.

Constraints enforced:
  Column perspective (data rows → IPIN columns):
  - Each Left/Right wire data row  → exactly 2 I00/I01 column connections
  - Each Bottom/Top wire data row  → exactly 2 I02/I03 column connections
  Row perspective (wire columns → IPIN rows, tap zero only):
  - Each Left wire column (in IPIN rows)   → exactly 2 I00/I01 row connections
  - Each Bottom wire column (in IPIN rows) → exactly 2 I02/I03 row connections
  General:
  - Total fan-in is equalized across all I0X pins
  - Each IPIN uses ONE uniform delay value for all its connections
  - IC0 columns, IC0 IPIN rows, and OPIN rows are NOT modified

Directional mapping:
  Columns: I00/I01 ↔ Left+Right wires;  I02/I03 ↔ Bottom+Top wires
  Rows:    I00/I01 ↔ Left wires only;    I02/I03 ↔ Bottom wires only
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


def find_direction_column_ranges(header_row):
    """
    Parse the first header row to find which columns belong to each direction group.

    Handles two header formats:
      - Sparse: label at start of group, rest empty (,,,,Left,,,,,Right,,,,)
      - Repeated: label in every cell (,,,,Left,Left,Left,...,Right,Right,...)

    Returns:
        dict: direction_name -> list of column indices
    """
    known_labels = {'Left', 'Right', 'Top', 'Bottom', 'IPIN'}
    ranges = defaultdict(list)

    for i, cell in enumerate(header_row):
        label = cell.strip()
        if label in known_labels:
            ranges[label].append(i)

    total_labeled = sum(len(cols) for cols in ranges.values())

    if total_labeled <= len(known_labels):
        # Sparse format: infer range from label position to next label
        dir_positions = sorted(
            [(i, cell.strip()) for i, cell in enumerate(header_row)
             if cell.strip() in known_labels]
        )
        ranges = {}
        for idx, (start_col, name) in enumerate(dir_positions):
            if idx + 1 < len(dir_positions):
                end_col = dir_positions[idx + 1][0] - 1
            else:
                end_col = len(header_row) - 1
            ranges[name] = list(range(start_col, end_col + 1))
    else:
        ranges = dict(ranges)

    return ranges


def find_ipin_columns(direction_col_ranges):
    """Return the IPIN column indices from the direction ranges."""
    return direction_col_ranges.get('IPIN', [])


def classify_ipin_columns(rows, ipin_indices, pin_name_row=4):
    """
    Classify each IPIN column by its pin type (I00, I01, I02, I03, IC0)
    based on pin names in the designated header row.

    Returns:
        column_types:     dict col_idx -> pin type string
        column_pin_names: dict col_idx -> full pin name (e.g., 'clb.I00[0]')
    """
    column_types = {}
    column_pin_names = {}
    pin_row = rows[pin_name_row]

    for col_idx in ipin_indices:
        if col_idx < len(pin_row):
            pin_name = pin_row[col_idx].strip()
            column_pin_names[col_idx] = pin_name
            match = re.match(r'clb\.(I\d{2}|IC\d)\[', pin_name)
            if match:
                column_types[col_idx] = match.group(1)
            else:
                column_types[col_idx] = 'other'
        else:
            column_types[col_idx] = 'other'
            column_pin_names[col_idx] = ''

    return column_types, column_pin_names


def find_ipin_rows(rows, header_rows=5):
    """
    Find IPIN rows at the bottom of the CSV.

    Returns:
        dict: pin_name -> row_index (e.g., 'clb.I00[0]' -> 346)
    """
    ipin_rows = {}
    for row_idx in range(header_rows, len(rows)):
        row = rows[row_idx]
        if len(row) > 3 and row[0].strip() == 'IPIN':
            pin_name = row[3].strip()
            if pin_name:
                ipin_rows[pin_name] = row_idx
    return ipin_rows


def collect_all_delays_for_ipin(col_idx, rows, column_pin_names, column_types,
                                 ipin_row_map, data_row_indices, direction_col_ranges):
    """
    Collect ALL numeric delay values for one IPIN from both perspectives:
      - Column perspective: values in its IPIN column across data rows
      - Row perspective: values in its IPIN row across relevant wire columns

    Returns a list of float delay values.
    """
    values = []
    pin_name = column_pin_names.get(col_idx, '')
    pin_type = column_types.get(col_idx)

    # Column perspective: scan the IPIN column across data rows
    for row_idx in data_row_indices:
        row = rows[row_idx]
        if col_idx < len(row) and row[col_idx].strip():
            try:
                values.append(float(row[col_idx]))
            except ValueError:
                pass

    # Row perspective: scan the IPIN row across relevant wire columns
    if pin_name in ipin_row_map:
        ipin_row = rows[ipin_row_map[pin_name]]
        if pin_type in ('I00', 'I01'):
            wire_cols = direction_col_ranges.get('Left', [])
        elif pin_type in ('I02', 'I03'):
            wire_cols = direction_col_ranges.get('Bottom', [])
        else:
            wire_cols = []

        for wc in wire_cols:
            if wc < len(ipin_row) and ipin_row[wc].strip():
                try:
                    values.append(float(ipin_row[wc]))
                except ValueError:
                    pass

    return values


def compute_balanced_targets(pin_cols, total_budget):
    """
    Distribute a total budget evenly across pins: each gets base or base+1.

    Args:
        pin_cols:     list of IPIN column indices
        total_budget: total connections to distribute among these pins

    Returns:
        dict: col_idx -> target count (int)
    """
    num_pins = len(pin_cols)
    if num_pins == 0:
        return {}

    base = total_budget // num_pins
    remainder = total_budget % num_pins

    # Shuffle so the +1 extras are randomly assigned
    shuffled = list(pin_cols)
    random.shuffle(shuffled)

    targets = {}
    for i, col in enumerate(shuffled):
        targets[col] = base + (1 if i < remainder else 0)

    return targets


def greedy_distribute(items, slots, target_per_slot):
    """
    Generic greedy assignment: each item picks 2 slots, targeting balanced counts.

    Each "item" gets exactly 2 "slot" assignments. Slots are filled toward
    their target counts. Items are shuffled; ties broken randomly.

    Args:
        items: list of item identifiers (e.g., row indices or column indices)
        slots: list of slot identifiers (e.g., IPIN column indices or IPIN row indices)
        target_per_slot: dict slot -> target count

    Returns:
        assignment: dict item -> [slot1, slot2]
        fill:       dict slot -> actual count assigned
    """
    fill = {s: 0 for s in slots}
    assignment = {item: [] for item in items}

    shuffled_items = list(items)
    random.shuffle(shuffled_items)

    def pick_best(exclude):
        available = [
            (s, target_per_slot[s] - fill[s])
            for s in slots if s not in exclude
        ]
        if not available:
            return None
        max_deficit = max(d for _, d in available)
        best = [s for s, d in available if d == max_deficit]
        return random.choice(best)

    for item in shuffled_items:
        for _ in range(2):
            slot = pick_best(assignment[item])
            if slot is not None:
                assignment[item].append(slot)
                fill[slot] += 1

    return assignment, fill


def redistribute_connections(rows, ipin_indices, column_types, column_pin_names,
                             direction_col_ranges, header_rows=5):
    """
    Main redistribution logic.

    Steps:
      1. Compute one average delay per IPIN (from all existing column + row values).
      2. Clear I0X columns in all wire data rows AND I0X IPIN rows' wire columns.
      3. Compute balanced targets for column and row budgets independently.
      4. Distribute:
         - Column: Left+Right data rows → 2 I00/I01 each; Bottom+Top data rows → 2 I02/I03 each
         - Row:    Left wire cols → 2 I00/I01 IPIN rows each; Bottom wire cols → 2 I02/I03 each
      5. Write the uniform per-IPIN delay value into all assigned cells.
      6. IC0 is never modified.
    """
    # ---- Group IPIN columns by type ----
    i00_i01_cols = sorted(c for c in ipin_indices if column_types.get(c) in ('I00', 'I01'))
    i02_i03_cols = sorted(c for c in ipin_indices if column_types.get(c) in ('I02', 'I03'))
    ic0_cols = sorted(c for c in ipin_indices if column_types.get(c) == 'IC0')
    all_i0x_cols = i00_i01_cols + i02_i03_cols

    # ---- Direction wire column ranges ----
    left_wire_cols = direction_col_ranges.get('Left', [])
    bottom_wire_cols = direction_col_ranges.get('Bottom', [])

    # ---- Find IPIN rows ----
    ipin_row_map = find_ipin_rows(rows, header_rows)
    print(f"Found {len(ipin_row_map)} IPIN rows")

    # ---- Classify data rows by direction ----
    left_rows = []
    right_rows = []
    top_rows = []
    bottom_rows = []

    for row_idx in range(header_rows, len(rows)):
        direction = rows[row_idx][0].strip()
        if direction == 'Left':
            left_rows.append(row_idx)
        elif direction == 'Right':
            right_rows.append(row_idx)
        elif direction == 'Top':
            top_rows.append(row_idx)
        elif direction == 'Bottom':
            bottom_rows.append(row_idx)

    all_wire_rows = left_rows + right_rows + top_rows + bottom_rows

    print(f"\nData rows: Left={len(left_rows)}, Right={len(right_rows)}, "
          f"Top={len(top_rows)}, Bottom={len(bottom_rows)}")
    print(f"I0X columns: I00/I01={len(i00_i01_cols)}, I02/I03={len(i02_i03_cols)}")
    print(f"IC0 columns (unchanged): {len(ic0_cols)}")
    print(f"Wire columns: Left={len(left_wire_cols)}, Bottom={len(bottom_wire_cols)}")

    # ================================================================
    # STEP 1: Compute one uniform delay per IPIN (before clearing)
    # ================================================================
    # Average all numeric values from both the IPIN column (data rows)
    # and the IPIN row (wire columns) to get a single representative delay.
    ipin_delay = {}
    all_delays = []
    for col_idx in all_i0x_cols:
        vals = collect_all_delays_for_ipin(
            col_idx, rows, column_pin_names, column_types,
            ipin_row_map, all_wire_rows, direction_col_ranges
        )
        if vals:
            avg = sum(vals) / len(vals)
            ipin_delay[col_idx] = avg
            all_delays.extend(vals)
        # (pins with no values will use fallback below)

    # Fallback for pins that had no numeric values
    fallback = sum(all_delays) / len(all_delays) if all_delays else 250
    for col_idx in all_i0x_cols:
        if col_idx not in ipin_delay:
            ipin_delay[col_idx] = fallback

    # ================================================================
    # STEP 2: Clear all I0X connections (columns in data rows + rows)
    # ================================================================
    # Clear I0X columns in ALL wire data rows
    for row_idx in all_wire_rows:
        row = rows[row_idx]
        for col_idx in all_i0x_cols:
            if col_idx < len(row):
                row[col_idx] = ''

    # Clear wire columns in I0X IPIN rows
    # I00/I01 IPIN rows: clear Left wire columns
    # I02/I03 IPIN rows: clear Bottom wire columns
    for col_idx in all_i0x_cols:
        pin_name = column_pin_names.get(col_idx, '')
        pin_type = column_types.get(col_idx)
        if pin_name not in ipin_row_map:
            continue
        ipin_row_idx = ipin_row_map[pin_name]
        row = rows[ipin_row_idx]

        if pin_type in ('I00', 'I01'):
            wire_cols = left_wire_cols
        else:
            wire_cols = bottom_wire_cols

        for wc in wire_cols:
            if wc < len(row):
                row[wc] = ''

    # ================================================================
    # STEP 3: Compute targets for both column and row budgets
    # ================================================================
    def compute_and_log(pin_cols, num_data_items, num_wire_items, group_name):
        """
        Compute column and row targets for one group.

        Column budget = 2 * num_data_items (each data row → 2 column connections)
        Row budget    = 2 * num_wire_items (each wire column → 2 row connections)
        Total per pin = (col_budget + row_budget) / num_pins

        Returns:
            col_targets: dict col_idx -> target column connections
            row_targets: dict col_idx -> target row connections
        """
        num_pins = len(pin_cols)
        if num_pins == 0:
            print(f"\n{group_name}: no pins, skipping")
            return {}, {}

        col_budget = 2 * num_data_items
        row_budget = 2 * num_wire_items
        total = col_budget + row_budget

        print(f"\n{group_name}:")
        print(f"  Pins: {num_pins}")
        print(f"  Column budget: 2 x {num_data_items} data rows = {col_budget}")
        print(f"  Row budget:    2 x {num_wire_items} wire cols  = {row_budget}")
        print(f"  Total fan-in:  {total}  →  {total / num_pins:.1f} per pin")

        col_targets = compute_balanced_targets(pin_cols, col_budget)
        row_targets = compute_balanced_targets(pin_cols, row_budget)

        for c in pin_cols:
            pin = column_pin_names.get(c, f"col{c}")
            ct = col_targets.get(c, 0)
            rt = row_targets.get(c, 0)
            delay = ipin_delay.get(c, 0)
            print(f"    {pin}: col={ct}, row={rt}, total={ct + rt}, delay={delay:.0f}")

        return col_targets, row_targets

    # Column connections: Left+Right → I00/I01, Bottom+Top → I02/I03
    # Row connections (tap zero): Left only → I00/I01, Bottom only → I02/I03
    i00_i01_col_tgt, i00_i01_row_tgt = compute_and_log(
        i00_i01_cols, len(left_rows) + len(right_rows), len(left_wire_cols),
        "I00/I01 group (cols: Left+Right, rows: Left)"
    )
    i02_i03_col_tgt, i02_i03_row_tgt = compute_and_log(
        i02_i03_cols, len(bottom_rows) + len(top_rows), len(bottom_wire_cols),
        "I02/I03 group (cols: Bottom+Top, rows: Bottom)"
    )

    # ================================================================
    # STEP 4: Distribute column connections (data rows → IPIN columns)
    # ================================================================
    print("\nDistributing column connections...")

    # Left+Right data rows → 2 I00/I01 columns each
    col_assign_lr, col_fill_lr = greedy_distribute(left_rows + right_rows, i00_i01_cols, i00_i01_col_tgt)
    # Bottom+Top data rows → 2 I02/I03 columns each
    col_assign_bt, col_fill_bt = greedy_distribute(bottom_rows + top_rows, i02_i03_cols, i02_i03_col_tgt)

    # Write column connections into data rows
    for row_idx, assigned_cols in {**col_assign_lr, **col_assign_bt}.items():
        row = rows[row_idx]
        # Extend row if needed
        max_col = max(all_i0x_cols) + 1
        while len(row) < max_col:
            row.append('')
        for col_idx in assigned_cols:
            delay = ipin_delay.get(col_idx, fallback)
            row[col_idx] = f"{delay:.0f}"

    # ================================================================
    # STEP 5: Distribute row connections (wire cols → IPIN rows)
    # ================================================================
    # For each wire column, pick 2 IPIN rows to connect to.
    # This is the same greedy algorithm but writing into IPIN rows.
    print("Distributing row connections...")

    # Left wire cols → 2 I00/I01 IPIN rows each
    row_assign_lr, row_fill_lr = greedy_distribute(left_wire_cols, i00_i01_cols, i00_i01_row_tgt)
    # Bottom wire cols → 2 I02/I03 IPIN rows each
    row_assign_bt, row_fill_bt = greedy_distribute(bottom_wire_cols, i02_i03_cols, i02_i03_row_tgt)

    # Write row connections into IPIN rows
    for wire_col, assigned_pins in {**row_assign_lr, **row_assign_bt}.items():
        for col_idx in assigned_pins:
            pin_name = column_pin_names.get(col_idx, '')
            if pin_name not in ipin_row_map:
                continue
            ipin_row_idx = ipin_row_map[pin_name]
            row = rows[ipin_row_idx]
            # Extend row if needed
            while len(row) <= wire_col:
                row.append('')
            delay = ipin_delay.get(col_idx, fallback)
            row[wire_col] = f"{delay:.0f}"

    # ================================================================
    # STEP 6: Verification
    # ================================================================
    print("\n=== Verification ===")

    # Column: each Left+Right row has exactly 2 I00/I01 connections
    wrong_lr_col = sum(
        1 for r in left_rows + right_rows
        if sum(1 for c in i00_i01_cols if c < len(rows[r]) and rows[r][c].strip()) != 2
    )
    print(f"Left+Right rows without exactly 2 I00/I01 column connections: {wrong_lr_col}")

    # Column: each Bottom+Top row has exactly 2 I02/I03 connections
    wrong_bt_col = sum(
        1 for r in bottom_rows + top_rows
        if sum(1 for c in i02_i03_cols if c < len(rows[r]) and rows[r][c].strip()) != 2
    )
    print(f"Bottom+Top rows without exactly 2 I02/I03 column connections: {wrong_bt_col}")

    # Column: Left+Right rows have zero I02/I03 connections (wrong group)
    cross_violations_lr = sum(
        1 for r in left_rows + right_rows
        for c in i02_i03_cols if c < len(rows[r]) and rows[r][c].strip()
    )
    print(f"I02/I03 column connections in Left+Right rows (should be 0): {cross_violations_lr}")

    # Column: Bottom+Top rows have zero I00/I01 connections (wrong group)
    cross_violations_bt = sum(
        1 for r in bottom_rows + top_rows
        for c in i00_i01_cols if c < len(rows[r]) and rows[r][c].strip()
    )
    print(f"I00/I01 column connections in Bottom+Top rows (should be 0): {cross_violations_bt}")

    # Row: each Left wire col connects to exactly 2 I00/I01 IPIN rows
    wrong_left_row = 0
    for wc in left_wire_cols:
        cnt = sum(1 for c in i00_i01_cols
                  if column_pin_names.get(c, '') in ipin_row_map
                  and wc < len(rows[ipin_row_map[column_pin_names[c]]])
                  and rows[ipin_row_map[column_pin_names[c]]][wc].strip())
        if cnt != 2:
            wrong_left_row += 1
    print(f"Left wire cols without exactly 2 I00/I01 row connections: {wrong_left_row}")

    # Row: each Bottom wire col connects to exactly 2 I02/I03 IPIN rows
    wrong_bot_row = 0
    for wc in bottom_wire_cols:
        cnt = sum(1 for c in i02_i03_cols
                  if column_pin_names.get(c, '') in ipin_row_map
                  and wc < len(rows[ipin_row_map[column_pin_names[c]]])
                  and rows[ipin_row_map[column_pin_names[c]]][wc].strip())
        if cnt != 2:
            wrong_bot_row += 1
    print(f"Bottom wire cols without exactly 2 I02/I03 row connections: {wrong_bot_row}")

    # Total fan-in per pin
    print("\nTotal fan-in per I0X pin (col + row):")
    all_fanins = []
    for col_idx in i00_i01_cols + i02_i03_cols:
        pin = column_pin_names.get(col_idx, f"col{col_idx}")
        if col_idx in i00_i01_cols:
            cf = col_fill_lr.get(col_idx, 0)
            rf = row_fill_lr.get(col_idx, 0)
        else:
            cf = col_fill_bt.get(col_idx, 0)
            rf = row_fill_bt.get(col_idx, 0)
        total = cf + rf
        all_fanins.append(total)
        print(f"  {pin}: col={cf}, row={rf}, total={total}, delay={ipin_delay.get(col_idx, 0):.0f}")

    if all_fanins:
        print(f"\nFan-in summary: min={min(all_fanins)}, max={max(all_fanins)}, "
              f"spread={max(all_fanins) - min(all_fanins)}")

    return rows


def main():
    parser = argparse.ArgumentParser(
        description='Modify I0X IPIN connections in switchbox CSV files'
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

    # ---- Find direction column ranges ----
    direction_col_ranges = find_direction_column_ranges(rows[0])

    # ---- Find and classify IPIN columns ----
    ipin_indices = find_ipin_columns(direction_col_ranges)
    if not ipin_indices:
        print("Error: No IPIN columns found")
        return 1
    print(f"Found {len(ipin_indices)} IPIN columns (indices {min(ipin_indices)} to {max(ipin_indices)})")

    column_types, column_pin_names = classify_ipin_columns(rows, ipin_indices, args.pin_name_row)
    type_counts = defaultdict(int)
    for col_type in column_types.values():
        type_counts[col_type] += 1
    print(f"Column types: {dict(type_counts)}")
    for dir_name, cols in sorted(direction_col_ranges.items()):
        if cols:
            print(f"  {dir_name} columns: {cols[0]}-{cols[-1]} ({len(cols)} cols)")

    # ---- Redistribute ----
    rows = redistribute_connections(
        rows, ipin_indices, column_types, column_pin_names,
        direction_col_ranges, args.header_rows
    )

    # ---- Write output ----
    print(f"\nWriting: {output_path}")
    write_csv(output_path, rows)
    print("Done!")

    return 0


if __name__ == '__main__':
    exit(main())
