import os
import re
import matplotlib.pyplot as plt

def get_run_dirs(base_dir):
    """Finds all subdirectories matching 'runXXX' (starting from run002)."""
    run_dirs = sorted(
        [d for d in os.listdir(base_dir) if re.match(r"run\d{3}$", d)],
        key=lambda x: int(x[3:])  # Sort numerically (run002, run003, ...)
    )
    return [d for d in run_dirs if int(d[3:]) >= 2]  # Ignore run001

def find_rr_graph_analysis_files(base_dir):
    """Finds all rr_graph_analysis.rpt files in subdirectories of base_dir."""

    run_dir_names = get_run_dirs(base_dir)
    files = []
    for run_dir_name in run_dir_names:
        circuit_dir = os.path.join(base_dir, run_dir_name, \
                                   "3d_SB_inter_die_stratixiv_arch.timing.xml", \
                                    "mes_noc_stratixiv_arch_timing.blif", "common")
        files.append((run_dir_name, os.path.join(circuit_dir, "rr_graph_analysis.rpt")))

    return files

def extract_inter_die_connections(file_path):
    """Extracts the 0->1 and 1->0 inter-die connection values from the given file."""
    pattern = r"Average number of inter-die connections per tile: 0->1: ([\d\.]+) - 1->0: ([\d\.]+)"
    with open(file_path, "r") as file:
        for line in file:
            match = re.search(pattern, line)
            if match:
                return float(match.group(1)), float(match.group(2))
    return None, None  # Return None if not found

def collect_data(base_dir):
    """Collects inter-die connection values from all rr_graph_analysis.txt files."""
    files = find_rr_graph_analysis_files(base_dir)
    data = {}
    for run_dir_name, file in files:
        print(f"Processing {run_dir_name} {file}")
        val_0_to_1, val_1_to_0 = extract_inter_die_connections(file)
        if val_0_to_1 is not None and val_1_to_0 is not None:
            data[run_dir_name] = (val_0_to_1, val_1_to_0)
    return data

def plot_data(data):
    """Plots the extracted inter-die connection values in two subcharts."""
    subdirs = list(data.keys())
    values_0_to_1 = [data[subdir][0] for subdir in subdirs]
    values_1_to_0 = [data[subdir][1] for subdir in subdirs]

    fig, axs = plt.subplots(2, 1, figsize=(10, 8))

    # Plot for 0->1 connections
    axs[0].bar(subdirs, values_0_to_1, color='b')
    axs[0].set_ylabel("0->1 Connections")
    axs[0].set_title("Average Inter-Die Connections Per Tile (0->1)")
    axs[0].tick_params(axis='x', rotation=45)

    # Plot for 1->0 connections
    axs[1].bar(subdirs, values_1_to_0, color='r')
    axs[1].set_ylabel("1->0 Connections")
    axs[1].set_title("Average Inter-Die Connections Per Tile (1->0)")
    axs[1].tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.show()

def main():
    # Main execution
    base_directory = "/home/mohagh18/vtr-verilog-to-routing/vtr_flow/tasks/regression_tests/vtr_reg_nightly_test7/3d_sb_titan_quick_qor_auto_bb"  # Replace with the actual base directory
    data = collect_data(base_directory)
    if data:
        plot_data(data)
    else:
        print("No valid data found in the given directory.")

if __name__ == "__main__":
    main()

