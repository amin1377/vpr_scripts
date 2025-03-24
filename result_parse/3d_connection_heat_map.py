import os
import re
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import plotly.express as px
import pandas as pd
import plotly.colors as pc

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
    for idx, run_dir_name in enumerate(run_dir_names):
        circuit_dir = os.path.join(base_dir, run_dir_name, \
                                   "3d_SB_inter_die_stratixiv_arch.timing.xml", \
                                    "mes_noc_stratixiv_arch_timing.blif", "common")
        files.append((run_dir_name, os.path.join(circuit_dir, "rr_graph_analysis.rpt")))
        break

    return files

def extract_rr_graph_data(file_path):
    """Extracts (x, y, layer) and corresponding values from the rr_graph_analysis.txt file."""
    pattern = re.compile(
        r"(\d+)\s+(\d+)\s+(\d+)\n\s+Number of inter-die connections:\s+(\d+)\n"
        r"\s+Average inter-die edge fan-in:\s+(\d+).*\n"
        r"\s+Average inter-die edge fan-out:\s+(\d+).*"
    )
    
    data = []
    with open(file_path, "r") as file:
        content = file.read()
        matches = pattern.findall(content)
        for match in matches:
            x, y, layer = map(int, match[:3])
            inter_die_connections = int(match[3])
            fan_in = int(match[4])
            fan_out = int(match[5])
            data.append((x, y, layer, inter_die_connections, fan_in, fan_out))
    
    return data

def create_2d_grid(data, metric_index):
    """Creates 2D NumPy grids for each Layer, ensuring one element per (X, Y) with Y increasing from bottom to top."""
    if not data:
        return None, None

    df = pd.DataFrame(data, columns=["X", "Y", "Layer", "Inter-Die Connections", "Fan-In", "Fan-Out"])

    # Get grid size
    max_x = df["X"].max() + 1
    max_y = df["Y"].max() + 1

    # Initialize a dictionary to store grids for each layer
    grids = {}

    for layer in df["Layer"].unique():
        layer_df = df[df["Layer"] == layer]  # Filter data for this layer

        # Initialize grid with NaN
        grid = np.full((max_x, max_y), np.nan)

        # Populate the grid
        for _, row in layer_df.iterrows():
            grid[row["X"], row["Y"]] = row[df.columns[metric_index + 3]]  # Select correct metric column

        # Flip the grid vertically so Y increases bottom to top
        grids[layer] = np.flipud(grid)

    return grids, df["Layer"].unique()


def generate_heatmap(data, metric_index, title, output_file):
    """Creates an interactive heatmap using Plotly with one element per (X, Y) and adaptive color scaling."""
    if not data:
        return None

    grids, layers = create_2d_grid(data, metric_index)

    for layer, grid in grids.items():
        # Flatten grid and remove NaNs for scaling
        valid_values = grid[~np.isnan(grid)].flatten()

        # Compute percentile-based vmin/vmax to reduce outlier impact
        if len(valid_values) > 0:
            vmin = np.percentile(valid_values, 5)   # 5th percentile (lower bound)
            vmax = np.percentile(valid_values, 95)  # 95th percentile (upper bound)
        else:
            vmin, vmax = None, None  # Auto-scale if no data

        # Use a diverging color scale to emphasize middle values
        colorscale = pc.get_colorscale("RdBu")  # Red-Blue diverging scale

        fig = px.imshow(
            grid.T,  # Transpose for correct orientation
            labels={"x": "X Coordinate", "y": "Y Coordinate", "color": title},
            color_continuous_scale=colorscale,
            title=f"{title} (Layer {layer})",
            zmin=vmin,  # Lower limit of color scale
            zmax=vmax   # Upper limit of color scale
        )

        fig.show()


def process_directory(base_dir):
    """Processes each run directory and generates heatmaps for inter-die connections, fan-in, and fan-out."""
    files = find_rr_graph_analysis_files(base_dir)
    for run_dir_name, file in files:
        print(f"Processing {run_dir_name} {file}")
        data = extract_rr_graph_data(file)

        if data:
            generate_heatmap(data, 0, f"Inter-Die Connections - {run_dir_name}", f"{run_dir_name}_inter_die_connections")
            generate_heatmap(data, 1, f"Average Fan-In - {run_dir_name}", f"{run_dir_name}_average_fan_in")
            generate_heatmap(data, 2, f"Average Fan-Out - {run_dir_name}", f"{run_dir_name}_average_fan_out")

def main():
    base_directory = "/home/mohagh18/vtr-verilog-to-routing/vtr_flow/tasks/regression_tests/vtr_reg_nightly_test7/3d_sb_titan_quick_qor_auto_bb"
    process_directory(base_directory)

if __name__ == "__main__":
    main()