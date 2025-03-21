import os
import argparse
import csv
import xml.etree.ElementTree as ET
import re
import pandas as pd
import numpy as np

# CIRCUITS = ["carpat_stratixiv_arch_timing", "JPEG_stratixiv_arch_timing", "picosoc_stratixiv_arch_timing", "sudoku_check_stratixiv_arch_timing", \
#             "CH_DFSIN_stratixiv_arch_timing", "leon2_stratixiv_arch_timing", "radar20_stratixiv_arch_timing", "SURF_desc_stratixiv_arch_timing", \
#             "CHERI_stratixiv_arch_timing", "leon3mp_stratixiv_arch_timing", "random_stratixiv_arch_timing", "ucsb_152_tap_fir_stratixiv_arch_timing", \
#             "EKF-SLAM_Jacobians_stratixiv_arch_timing", "MCML_stratixiv_arch_timing", "Reed_Solomon_stratixiv_arch_timing", \
#             "uoft_raytracer_stratixiv_arch_timing", "fir_cascade_stratixiv_arch_timing", "MMM_stratixiv_arch_timing", "smithwaterman_stratixiv_arch_timing", \
#             "wb_conmax_stratixiv_arch_timing", "jacobi_stratixiv_arch_timing", "murax_stratixiv_arch_timing", "stap_steering_stratixiv_arch_timing"]
CIRCUITS = ["gsm_switch_stratixiv_arch_timing", "mes_noc_stratixiv_arch_timing", "dart_stratixiv_arch_timing", "denoise_stratixiv_arch_timing", \
            "sparcT2_core_stratixiv_arch_timing", "cholesky_bdti_stratixiv_arch_timing", "minres_stratixiv_arch_timing", "stap_qrd_stratixiv_arch_timing", \
            "openCV_stratixiv_arch_timing", "bitonic_mesh_stratixiv_arch_timing", "segmentation_stratixiv_arch_timing", "SLAM_spheric_stratixiv_arch_timing", \
            "des90_stratixiv_arch_timing", "neuron_stratixiv_arch_timing", "sparcT1_core_stratixiv_arch_timing", "stereo_vision_stratixiv_arch_timing", \
            "cholesky_mc_stratixiv_arch_timing", "bitcoin_miner_stratixiv_arch_timing", "sparcT1_chip2_stratixiv_arch_timing", \
            "LU_Network_stratixiv_arch_timing"]
BLOCK_TYPES = ["LAB", "DSP", "M9K", "M144K", "io", "PLL"]

def get_run_dirs(base_dir):
    """Finds all subdirectories matching 'runXXX' (starting from run002)."""
    run_dirs = sorted(
        [d for d in os.listdir(base_dir) if re.match(r"run\d{3}$", d)],
        key=lambda x: int(x[3:])  # Sort numerically (run002, run003, ...)
    )
    return [d for d in run_dirs if int(d[3:]) >= 2]  # Ignore run001

def extract_block_data(net_file, circuit_name):
    """Extracts block names and their types from the VPR netlist XML file."""
    def clean_instance(instance):
        """Removes [number] from instance name"""
        return re.sub(r'\[\d+\]', '', instance)

    tree = ET.parse(net_file)
    root = tree.getroot()
    
    assert root.attrib["name"] == f"{circuit_name}.net", f"Expected {circuit_name}.net, but got {root.attrib['name']}"
    

    # Iterate over its immediate child <block> elements
    block_map = {}
    type_map = {}
    for child in root.findall("block"):
        block_name = child.get("name")
        block_type = clean_instance(child.get("instance", ""))
        assert block_name not in block_map, f"Duplicate block name: {block_name}"
        block_map[block_name] = block_type
        if block_type not in type_map:
            type_map[block_type] = []
        type_map[block_type].append(block_name)
        
    return block_map, type_map

def count_blocks_by_layer(circuit_name, run_dir):
    net_file_path = os.path.join(run_dir, f"{circuit_name}.net")
    place_file_path = os.path.join(run_dir, f"{circuit_name}.place")
    blocks_type_layer = {}
    found_block_name = False

    block_map, type_map = extract_block_data(net_file_path, circuit_name)

    for type in BLOCK_TYPES:
        blocks_type_layer[type] = [0, 0]

    with open(place_file_path, 'r') as file:
        for line in file:
            line = line.strip()

            if not found_block_name:
                if line.startswith("#block name"):
                    found_block_name = True
                continue

            if line.startswith("#"):
                continue

            columns = line.split("\t")
            block_name = columns[0]
            layer_num = int(columns[-2])
            block_type = block_map[block_name]
            blocks_type_layer[block_type][layer_num] += 1

    return blocks_type_layer

def get_run_data(directory):
    circuit_block_type_layer = {}
    data = []
    data.append(["Circuit", "Layer #0", "Layer #1"])
    for idx, circuit_name in enumerate(CIRCUITS):
        subdir_path = os.path.join(directory, f"{circuit_name}.blif", "common")
        if os.path.isdir(subdir_path):
            print(f"\tProcessing {circuit_name}")
            blocks_type_layer = count_blocks_by_layer(circuit_name, subdir_path)
            circuit_block_type_layer[circuit_name] = blocks_type_layer
            # if idx >= 1:
            #     break
        else:
            print(f"\tCouldn't find {subdir_path}")
    

    num_block_types = len(BLOCK_TYPES)
    row = []
    table_data = []
    row.append("")
    row.append("Layer #0")
    for _ in range(num_block_types-1):
        row.append(f"")
    row.append("Layer #1")
    for _ in range(num_block_types-1):
        row.append(f"")
    table_data.append(row)

    row = []
    row.append("Circuit")
    for _ in [0, 1]:
        for block_type in BLOCK_TYPES:
            row.append(block_type)
    table_data.append(row)

    for circuit_name, blocks_type_layer in circuit_block_type_layer.items():
        row = []
        row.append(circuit_name)
        circuit_num_blocks = circuit_block_type_layer[circuit_name]
        total_num_block_per_type = {}
        for block_type in BLOCK_TYPES:
            if block_type not in circuit_num_blocks:
                total_num_block_per_type[block_type] = 0.0
            else:
                total_num_block_per_type[block_type] = circuit_num_blocks[block_type][0] + circuit_num_blocks[block_type][1]
        for layer_num in [0, 1]:
            for block_type in BLOCK_TYPES:
                if block_type not in circuit_num_blocks or total_num_block_per_type[block_type] == 0:
                    row.append(0)
                else:
                    row.append(f"{circuit_num_blocks[block_type][layer_num]/total_num_block_per_type[block_type]:.2f}")
        table_data.append(row)

    return table_data

def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_dir", required=True, help="File that contains the actual results")
    parser.add_argument("--out_file_name", required=True, help="Name of the output file")

    args = parser.parse_args()
    return args

def get_average_table_data(run_dir_table_data):
    """Computes element-wise average of all numerical columns, preserving headers and circuit names from the first table."""
    
    # Extract all tables as lists
    table_list = list(run_dir_table_data.values())
    print(table_list)
    if not table_list:
        return []

    # Use the first table as a reference for headers & circuit names
    reference_table = table_list[0]
    num_rows = len(reference_table)
    num_cols = len(reference_table[0])

    # Initialize sum and count arrays for numerical values
    sum_array = np.zeros((num_rows, num_cols), dtype=float)
    count_array = np.zeros((num_rows, num_cols), dtype=int)

    # Process each table for numerical values (excluding first two rows and first column)
    for table in table_list:
        for r in range(2, num_rows):  # Start from 3rd row
            for c in range(1, num_cols):  # Start from 2nd column
                try:
                    value = float(table[r][c])  # Convert to float
                    sum_array[r][c] += value
                    count_array[r][c] += 1
                except ValueError:
                    pass  # Ignore non-numeric values

    # Compute averages (avoid division by zero)
    avg_array = np.divide(sum_array, count_array, out=np.zeros_like(sum_array), where=count_array != 0)

    # Construct the final averaged table (copy headers and circuit names from first table)
    final_table = [row[:] for row in reference_table]  # Deep copy reference table

    # Insert the averaged values into the final table
    for r in range(2, num_rows):
        for c in range(1, num_cols):
            final_table[r][c] = f"{avg_array[r][c]:.2f}"

    return final_table

def main(task_dir, out_file_name):
    run_dirs = get_run_dirs(task_dir)
    run_dir_table_data = {}
    for idx, run_dir_name in enumerate(run_dirs):
        print(f"Processing {run_dir_name}")
        run_dir = os.path.join(task_dir, run_dir_name, "3d_SB_inter_die_stratixiv_arch.timing.xml")
        table_data = get_run_data(run_dir)
        run_dir_table_data[run_dir_name] = table_data
        # if idx >= 1:
        #     break
    
    run_dir_table_data["avg"] = get_average_table_data(run_dir_table_data)

    for run_dir_name, table_data in run_dir_table_data.items():
        run_dir_table_data[run_dir_name] = pd.DataFrame(table_data[1:], columns=table_data[0])
    with pd.ExcelWriter(out_file_name, engine="xlsxwriter") as writer:
        for run_dir_name, table_data in run_dir_table_data.items():
            table_data.to_excel(writer, sheet_name=run_dir_name, index=False)
    print(f"Saved to {out_file_name}")

if __name__ == "__main__":
    args = getArgs()
    main(args.task_dir, args.out_file_name)
