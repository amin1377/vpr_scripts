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
                print(f"Metic Name: {metric_name} - Regex pattern: {regex_pattern}")
                config_entries[output_file.strip()].append((metric_name.strip(), regex_pattern.strip()))

    return config_entries


def extract_metrics(config_entries, task_dir, metrics_map):
    """Processes each output file once and extracts multiple metrics."""

    for output_file, metric_patterns in config_entries.items():
        for metric_name, regex_pattern in metric_patterns:
            metrics_map[metric_name] = 0

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


def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_dir", required=True, help="File that contains the actual results")
    parser.add_argument("--out_file_name", required=True, help="Name of the output file")
    parser.add_argument("--config_file", required=True, help="Name of the config file")

    args = parser.parse_args()
    return args

def main():
    args = getArgs()
    config_entries = parse_config_file(args.config_file)

    table_data = []
    for idx, subdir in enumerate(os.listdir(args.task_dir)):
        if os.path.isdir(os.path.join(args.task_dir, subdir)):
            print(f"Processing {subdir}")
            circuit_name = subdir
            circuit_dir = os.path.join(args.task_dir, circuit_name, circuit_name)
            metrics_map = {}
            metrics_map["circuit"] = circuit_name
            extract_metrics(config_entries, circuit_dir, metrics_map)
            table_data.append(metrics_map)
    
    # Get column headers (Ensure "circuit" is the first column)
    headers = list(table_data[0].keys())  # Extract column order
    print(f"Headers: {headers}")

    # Write to TSV file using csv module
    with open(args.out_file_name, "w", newline="") as tsvfile:
        writer = csv.DictWriter(tsvfile, fieldnames=headers, delimiter="\t")
        
        writer.writeheader()  # Write column headers
        writer.writerows(table_data)  # Write data rows
    
if __name__ == "__main__":
    main()
