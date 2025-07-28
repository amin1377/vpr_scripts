import os
import re   
import argparse
import csv
from collections import defaultdict

def parse_config_file(config_filename):
    """Reads the config file and returns a dictionary {output_file: [(metric_name, regex_pattern)]}."""
    config_entries = defaultdict(list)

    with open(config_filename, "r") as config_file:
        for line in config_file:
            line = line.strip()
            if not line or line.startswith("#"):  # Skip empty lines and comments
                continue
            parts = line.split(";")
            if len(parts) == 3:
                metric_name, output_file, regex_pattern = parts
                print(f"Metric Name: {metric_name} - Regex pattern: {regex_pattern}")
                config_entries[output_file.strip()].append((metric_name.strip(), regex_pattern.strip()))

    return config_entries


def extract_metrics(config_entries, task_dir, metrics_map):
    """Processes each output file once and extracts multiple metrics."""

    for output_file, metric_patterns in config_entries.items():
        for metric_name, regex_pattern in metric_patterns:
            metrics_map[metric_name] = -1

    for output_file, metric_patterns in config_entries.items():
        try:
            with open(os.path.join(task_dir, output_file), "r") as file:
                for line in file:
                    for metric_name, regex_pattern in metric_patterns:
                        match = re.search(regex_pattern, line.strip())
                        if match:
                            metrics_map[metric_name] = match.group(1).strip()
        except FileNotFoundError:
            print(f"Warning: File '{os.path.join(task_dir, output_file)}' not found. Skipping related metrics.")
            for metric_name, _ in metric_patterns:
                metrics_map[metric_name] = None  # Mark all missing file's metrics as None

def create_comparison_table(tables_data):
    """Creates a comparison table with ratios between different task directories."""
    if not tables_data or len(tables_data) < 2:
        return []

    # Get all unique circuit names across all tables
    all_circuits = set()
    for table in tables_data:
        all_circuits.update(row['circuit'] for row in table)

    # Create a mapping of circuit names to their metrics for each table
    table_maps = []
    for table in tables_data:
        circuit_map = {row['circuit']: row for row in table}
        table_maps.append(circuit_map)

    # Create comparison rows
    comparison_rows = []
    for circuit in sorted(all_circuits):
        row = {'circuit': circuit}
        
        # Add metrics from each table
        for i, table_map in enumerate(table_maps):
            if circuit in table_map:
                for key, value in table_map[circuit].items():
                    if key != 'circuit':
                        row[f"{key}_{i+1}"] = value
            else:
                for key in table_maps[0][list(table_maps[0].keys())[0]].keys():
                    if key != 'circuit':
                        row[f"{key}_{i+1}"] = -1

        # Calculate ratios
        for i in range(1, len(table_maps)):
            for key in table_maps[0][list(table_maps[0].keys())[0]].keys():
                if key != 'circuit':
                    try:
                        val1 = float(row[f"{key}_1"])
                        val2 = float(row[f"{key}_{i+1}"])
                        if val1 != 0 and val1 != -1 and val2 != -1:
                            row[f"{key}_ratio_{i+1}"] = val2 / val1
                        else:
                            row[f"{key}_ratio_{i+1}"] = -1
                    except (ValueError, TypeError):
                        row[f"{key}_ratio_{i+1}"] = -1

        comparison_rows.append(row)

    return comparison_rows


def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task_dir",
        nargs='+',  # Accepts one or more values
        required=True,
        help="List of directories containing the circuits"
    )
    parser.add_argument("--out_file_name", required=True, help="Name of the output file")
    parser.add_argument("--config_file", required=True, help="Name of the config file")

    args = parser.parse_args()
    return args

def main():
    args = getArgs()
    config_entries = parse_config_file(args.config_file)

    tables_data = []
    for task_dir in args.task_dir:
        print(f"Processing {task_dir}")
        table_data = []
        for idx, subdir in enumerate(os.listdir(task_dir)):
            if os.path.isdir(os.path.join(task_dir, subdir)):
                print(f"Processing {subdir}")
                circuit_name = subdir
                circuit_dir = os.path.join(task_dir, circuit_name, circuit_name)
                metrics_map = {}
                metrics_map["circuit"] = circuit_name
                extract_metrics(config_entries, circuit_dir, metrics_map)
                table_data.append(metrics_map)
        tables_data.append(table_data)
    
    # Write individual tables
    for i, table_data in enumerate(tables_data):
        headers = list(table_data[0].keys())
        out_file = f"{os.path.splitext(args.out_file_name)[0]}_table{i+1}.tsv"
        
        with open(out_file, "w", newline="") as tsvfile:
            writer = csv.DictWriter(tsvfile, fieldnames=headers, delimiter="\t")
            writer.writeheader()
            writer.writerows(table_data)

    
    # Create and write comparison table
    comparison_rows = create_comparison_table(tables_data)
    if comparison_rows:
        # Get all possible headers for the comparison table
        all_headers = ['circuit']
        for key in tables_data[0][0].keys():
            if key != 'circuit':
                # Add original metric columns
                for i in range(len(tables_data)):
                    all_headers.append(f"{key}_{i+1}")
                # Add ratio columns
                for i in range(1, len(tables_data)):
                    all_headers.append(f"{key}_ratio_{i+1}")

        comparison_file = f"{os.path.splitext(args.out_file_name)[0]}_comparison.tsv"
        with open(comparison_file, "w", newline="") as tsvfile:
            writer = csv.DictWriter(tsvfile, fieldnames=all_headers, delimiter="\t")
            writer.writeheader()
            writer.writerows(comparison_rows)
    
if __name__ == "__main__":
    main()
