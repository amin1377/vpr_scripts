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


def extract_metrics(config_entries, circuit_dir, metrics_map):
    """Extracts metrics from files in circuit_dir into metrics_map."""
    for _, metric_patterns in config_entries.items():
        for metric_name, _ in metric_patterns:
            metrics_map.setdefault(metric_name, -1)

    for output_file, metric_patterns in config_entries.items():
        path = os.path.join(circuit_dir, output_file)
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


def get_global_metric_keys(all_task_data):
    """Union of metric keys across all tasks and seeds (excluding 'circuit'), sorted."""
    keys = set()
    for task_data in all_task_data:
        for seed_data in task_data.values():
            for row in seed_data:
                keys.update([k for k in row.keys() if k != "circuit"])
    return sorted(keys)


def write_seed_sheet(wb, sheet_name, rows, metric_keys):
    """Write one seed sheet with headers: ['circuit'] + metric_keys."""
    ws = wb.create_sheet(title=sheet_name)
    headers = ["circuit"] + metric_keys
    ws.append(headers)
    for r in rows:
        ws.append([r.get("circuit", "")] + [r.get(k, "") for k in metric_keys])


def calculate_averages(task_data, metric_keys):
    """
    Calculate average metrics across seeds for each circuit.
    Returns a list of dict rows with averaged values.
    """
    # Group data by circuit across all seeds
    circuit_metrics = defaultdict(lambda: defaultdict(list))
    
    for seed_data in task_data.values():
        for row in seed_data:
            circuit = row.get("circuit")
            if circuit:
                for metric in metric_keys:
                    value = row.get(metric)
                    if value is not None and value != "" and value != -1:
                        try:
                            # Try to convert to float for averaging
                            float_value = float(value)
                            circuit_metrics[circuit][metric].append(float_value)
                        except (ValueError, TypeError):
                            # If not numeric, just collect the values
                            circuit_metrics[circuit][metric].append(value)
    
    # Calculate averages
    averaged_data = []
    for circuit in sorted(circuit_metrics.keys()):
        row = {"circuit": circuit}
        for metric in metric_keys:
            values = circuit_metrics[circuit][metric]
            if values:
                # Check if all values are numeric
                try:
                    numeric_values = [float(v) for v in values]
                    row[metric] = sum(numeric_values) / len(numeric_values)
                except (ValueError, TypeError):
                    # If not all numeric, take the most common value or first value
                    row[metric] = values[0] if len(set(values)) == 1 else f"Mixed({len(values)})"
            else:
                row[metric] = ""
        averaged_data.append(row)
    
    return averaged_data


def build_comparison_sheet_with_averages(wb, all_task_data, metric_keys):
    """
    Create 'Comparison' sheet with AVERAGE formulas and ratio columns.
    For each metric and for each Task_i (i>=2), column = Task_i_avg / Task_1_avg via formula.
    """
    if not all_task_data or len(all_task_data) < 2:
        return  # nothing to compare

    ws = wb.create_sheet(title="Comparison")
    
    # Collect all circuits across all tasks and seeds
    all_circuits = set()
    for task_data in all_task_data:
        for seed_data in task_data.values():
            for row in seed_data:
                all_circuits.add(row.get("circuit"))
    circuits = sorted(all_circuits)

    num_tasks = len(all_task_data)
    
    # Create headers: circuit, then avg values for each task, then ratios
    headers = ["circuit"]
    
    # Add average columns for each task
    for task_idx in range(1, num_tasks + 1):
        for metric in metric_keys:
            headers.append(f"{metric}_avg_Task{task_idx}")
    
    # Add ratio columns (Task_i vs Task_1)
    for metric in metric_keys:
        for task_idx in range(2, num_tasks + 1):
            headers.append(f"{metric}_ratio_Task{task_idx}_vs_Task1")
    
    ws.append(headers)

    # Write data rows
    for r_idx, circuit in enumerate(circuits, start=2):
        ws.cell(row=r_idx, column=1, value=circuit)  # circuit name
        
        # Add AVERAGE formulas for each task
        task_avg_cols = {}  # Store column positions for ratio formulas
        col_ptr = 2
        
        for task_idx, task_data in enumerate(all_task_data):
            task_avg_cols[task_idx] = {}
            
            for m_idx, metric in enumerate(metric_keys):
                metric_col_letter = get_column_letter(2 + m_idx)  # B for first metric, etc.
                
                # Build list of seed sheet references for this task
                seed_refs = []
                for seed_name in sorted(task_data.keys()):
                    sheet_name = f"Task_{task_idx + 1}_{seed_name}"
                    # Use INDEX/MATCH to find the metric value for this circuit in this seed sheet
                    ref = f'INDEX({sheet_name}!${metric_col_letter}:${metric_col_letter}, MATCH($A{r_idx}, {sheet_name}!$A:$A, 0))'
                    seed_refs.append(ref)
                
                if seed_refs:
                    # Create AVERAGE formula across all seeds for this task and metric
                    avg_formula = f'=IFERROR(AVERAGE({", ".join(seed_refs)}), "")'
                    ws.cell(row=r_idx, column=col_ptr, value=avg_formula)
                else:
                    ws.cell(row=r_idx, column=col_ptr, value="")
                
                task_avg_cols[task_idx][metric] = get_column_letter(col_ptr)
                col_ptr += 1
        
        # Add ratio formulas using the average columns
        for metric in metric_keys:
            base_col = task_avg_cols[0][metric]  # Task_1 average column
            
            for task_idx in range(1, num_tasks):  # Task_2, Task_3, etc.
                compare_col = task_avg_cols[task_idx][metric]
                ratio_formula = f'=IFERROR({compare_col}{r_idx}/{base_col}{r_idx}, "")'
                ws.cell(row=r_idx, column=col_ptr, value=ratio_formula)
                col_ptr += 1


def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task_dir",
        nargs='+',
        required=True,
        help="List of directories containing seed directories with circuits"
    )
    parser.add_argument("--out_file_name", required=True, help="Output .xlsx file name")
    parser.add_argument("--config_file", required=True, help="Config file with metrics/regex")
    return parser.parse_args()


def main():
    args = getArgs()
    out_xlsx = args.out_file_name if args.out_file_name.lower().endswith(".xlsx") else f"{args.out_file_name}.xlsx"

    config_entries = parse_config_file(args.config_file)

    # Build all_task_data: list per task_dir; each task is dict per seed; each seed is list of dict rows
    all_task_data = []
    
    for task_idx, task_dir in enumerate(args.task_dir, start=1):
        print(f"Processing task_dir {task_idx}: {task_dir}")
        task_data = {}  # seed_name -> list of circuit rows
        
        # Look for seed directories
        for item in sorted(os.listdir(task_dir)):
            seed_path = os.path.join(task_dir, item)
            if os.path.isdir(seed_path) and item.startswith("seed_"):
                seed_name = item
                print(f"  Processing seed: {seed_name}")
                seed_data = []
                
                # Look for circuits within this seed directory
                for circuit_item in sorted(os.listdir(seed_path)):
                    circuit_outer = os.path.join(seed_path, circuit_item)
                    if os.path.isdir(circuit_outer):
                        circuit_name = circuit_item
                        circuit_dir = os.path.join(circuit_outer, circuit_name)  # <task_dir>/seed_X/<circuit>/<circuit>
                        
                        if os.path.isdir(circuit_dir):
                            print(f"    Circuit: {circuit_name} (dir: {circuit_dir})")
                            metrics_map = {"circuit": circuit_name}
                            extract_metrics(config_entries, circuit_dir, metrics_map)
                            seed_data.append(metrics_map)
                        else:
                            print(f"    Warning: Expected circuit directory not found: {circuit_dir}")
                
                task_data[seed_name] = seed_data
        
        all_task_data.append(task_data)

    wb = Workbook()
    wb.remove(wb.active)

    # Get consistent metric columns across all tasks and seeds
    metric_keys = get_global_metric_keys(all_task_data)

    # Write individual seed sheets for each task
    for task_idx, task_data in enumerate(all_task_data, start=1):
        for seed_name, seed_data in task_data.items():
            sheet_name = f"Task_{task_idx}_{seed_name}"
            write_seed_sheet(wb, sheet_name, seed_data, metric_keys)

    # Comparison sheet with averaged values and ratios
    build_comparison_sheet_with_averages(wb, all_task_data, metric_keys)

    wb.save(out_xlsx)
    print(f"✅ Wrote Excel report with seed-based analysis: {out_xlsx}")


if __name__ == "__main__":
    main()
