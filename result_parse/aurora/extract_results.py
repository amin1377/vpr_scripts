import os
import re
import argparse
from collections import defaultdict

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
except ImportError as e:
    raise SystemExit("This script requires 'openpyxl'. Install it with: pip install openpyxl") from e


def parse_config_file(config_filename):
    """Reads the config file and returns a dict: {output_file: [(metric_name, regex_pattern)]}."""
    config_entries = defaultdict(list)
    with open(config_filename, "r") as config_file:
        for line in config_file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            if len(parts) == 3:
                metric_name, output_file, regex_pattern = parts
                print(f"Metric Name: {metric_name} - Regex pattern: {regex_pattern}")
                config_entries[output_file.strip()].append((metric_name.strip(), regex_pattern.strip()))
    return config_entries


def extract_metrics(config_entries, task_dir, metrics_map):
    """Extracts metrics from files in task_dir into metrics_map."""
    for _, metric_patterns in config_entries.items():
        for metric_name, _ in metric_patterns:
            metrics_map.setdefault(metric_name, -1)

    for output_file, metric_patterns in config_entries.items():
        path = os.path.join(task_dir, output_file)
        try:
            with open(path, "r") as f:
                for line in f:
                    s = line.strip()
                    for metric_name, regex_pattern in metric_patterns:
                        if metrics_map.get(metric_name) not in (None, -1):
                            continue
                        m = re.search(regex_pattern, s)
                        if m:
                            metrics_map[metric_name] = m.group(1).strip()
        except FileNotFoundError:
            print(f"Warning: File '{path}' not found. Marking related metrics as None.")
            for metric_name, _ in metric_patterns:
                metrics_map[metric_name] = None


def get_global_metric_keys(tables_data):
    """Union of metric keys across all tables (excluding 'circuit'), sorted."""
    keys = set()
    for table in tables_data:
        for row in table:
            keys.update([k for k in row.keys() if k != "circuit"])
    return sorted(keys)


def write_task_sheet(wb, sheet_name, rows, metric_keys):
    """Write one task sheet with headers: ['circuit'] + metric_keys."""
    ws = wb.create_sheet(title=sheet_name)
    headers = ["circuit"] + metric_keys
    ws.append(headers)
    for r in rows:
        ws.append([r.get("circuit", "")] + [r.get(k, "") for k in metric_keys])


def build_comparison_sheet_ratios_only(wb, tables_data, metric_keys):
    """
    Create 'Comparison' sheet with ONLY ratio columns.
    For each metric and for each Task_i (i>=2), column = Task_i / Task_1 via formula:
      =IFERROR( INDEX(Task_i!$COL:$COL, MATCH($Arow, Task_i!$A:$A,0)) /
                INDEX(Task_1!$COL:$COL, MATCH($Arow, Task_1!$A:$A,0)), "" )
    """
    if not tables_data or len(tables_data) < 2:
        return  # nothing to compare

    ws = wb.create_sheet(title="Comparison")

    # Collect all circuits across tasks
    all_circuits = set()
    for table in tables_data:
        for row in table:
            all_circuits.add(row.get("circuit"))
    circuits = sorted(all_circuits)

    num_tasks = len(tables_data)
    # Header: A=circuit, then for each metric: metric_ratio_Task2, metric_ratio_Task3, ...
    headers = ["circuit"]
    for metric in metric_keys:
        for i in range(2, num_tasks + 1):
            headers.append(f"{metric}_ratio_Task{i}_vs_Task1")
    ws.append(headers)

    # In Task sheets, columns are: A=circuit, B=metric_keys[0], C=metric_keys[1], ...
    for r_idx, circuit in enumerate(circuits, start=2):
        ws.cell(row=r_idx, column=1, value=circuit)  # circuit name
        col_ptr = 2

        for m_idx, metric in enumerate(metric_keys):
            metric_col_letter = get_column_letter(2 + m_idx)  # B for first metric, etc.

            # Base address for Task_1 metric
            base_sheet = "Task_1"
            base_formula = (
                f'INDEX({base_sheet}!${metric_col_letter}:${metric_col_letter}, '
                f'MATCH($A{r_idx}, {base_sheet}!$A:$A, 0))'
            )

            # Ratios against Task_1 for each additional task
            for i in range(2, num_tasks + 1):
                sheet_name = f"Task_{i}"
                numer_formula = (
                    f'INDEX({sheet_name}!${metric_col_letter}:${metric_col_letter}, '
                    f'MATCH($A{r_idx}, {sheet_name}!$A:$A, 0))'
                )
                ratio_formula = f'=IFERROR(({numer_formula})/({base_formula}), "")'
                ws.cell(row=r_idx, column=col_ptr, value=ratio_formula)
                col_ptr += 1


def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task_dir",
        nargs='+',
        required=True,
        help="List of directories containing the circuits"
    )
    parser.add_argument("--out_file_name", required=True, help="Output .xlsx file name")
    parser.add_argument("--config_file", required=True, help="Config file with metrics/regex")
    return parser.parse_args()


def main():
    args = getArgs()
    out_xlsx = args.out_file_name if args.out_file_name.lower().endswith(".xlsx") else f"{args.out_file_name}.xlsx"

    config_entries = parse_config_file(args.config_file)

    # Build tables_data: list per task_dir; each table is list of dict rows
    tables_data = []
    for task_idx, task_dir in enumerate(args.task_dir, start=1):
        print(f"Processing task_dir {task_idx}: {task_dir}")
        table_data = []
        for sub in sorted(os.listdir(task_dir)):
            outer = os.path.join(task_dir, sub)
            if os.path.isdir(outer):
                circuit_name = sub
                circuit_dir = os.path.join(outer, circuit_name)  # <task_dir>/<circuit>/<circuit>
                print(f"  Circuit: {circuit_name} (dir: {circuit_dir})")
                metrics_map = {"circuit": circuit_name}
                extract_metrics(config_entries, circuit_dir, metrics_map)
                table_data.append(metrics_map)
        tables_data.append(table_data)

    wb = Workbook()
    wb.remove(wb.active)

    # Consistent metric columns across all Task sheets
    metric_keys = get_global_metric_keys(tables_data)

    # Write Task_i sheets
    for i, table_data in enumerate(tables_data, start=1):
        write_task_sheet(wb, f"Task_{i}", table_data, metric_keys)

    # Comparison sheet with ONLY ratio formulas (no raw values)
    build_comparison_sheet_ratios_only(wb, tables_data, metric_keys)

    wb.save(out_xlsx)
    print(f"✅ Wrote Excel report with ratio formulas only: {out_xlsx}")


if __name__ == "__main__":
    main()
