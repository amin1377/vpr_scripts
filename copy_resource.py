import os
import shutil
import argparse
import multiprocessing

def process_subdirectory(subdir, input_dir, output_dir):
    """Processes a single subdirectory in parallel."""
    subdir_path = os.path.join(input_dir, subdir)

    # Check if it's a directory and its name ends with ".blif"
    if not (os.path.isdir(subdir_path) and subdir.endswith(".blif")):
        return

    circuit_name = subdir[:-5]  # Remove ".blif" to get the circuit name
    common_dir = os.path.join(subdir_path, "common")

    if os.path.exists(common_dir):
        # Define file paths
        blif_file = os.path.join(common_dir, f"{circuit_name}.blif")
        net_file = os.path.join(common_dir, f"{circuit_name}.net")
        sdc_file = os.path.join(common_dir, f"{circuit_name}.sdc")
        rr_graph_file = os.path.join(common_dir, "rr_graph.xml")
        new_rr_graph_file = os.path.join(output_dir, f"rr_graph_{circuit_name}.xml")

        # Copy files if they exist
        for file in [blif_file, net_file, sdc_file]:
            assert os.path.exists(file), f"File {file} does not exist"
            shutil.copy(file, output_dir)
            print(f"Copied {file} → {output_dir}")

        # Copy and rename rr_graph.xml
        assert os.path.exists(rr_graph_file), f"File {rr_graph_file} does not exist"
        os.symlink(rr_graph_file, new_rr_graph_file)
        print(f"Linked {rr_graph_file} → {new_rr_graph_file}")

def process_directory(input_dir, output_dir, num_workers):
    """Processes all subdirectories in parallel."""
    os.makedirs(output_dir, exist_ok=True)  # Ensure output directory exists

    subdirs = os.listdir(input_dir)  # List of subdirectories
    with multiprocessing.Pool(num_workers) as pool:
        pool.starmap(process_subdirectory, [(subdir, input_dir, output_dir) for subdir in subdirs])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy and rename circuit files in parallel.")
    parser.add_argument("--input_dir", required=True, help="Path to the input directory")
    parser.add_argument("--output_dir", required=True, help="Path to the output directory")
    parser.add_argument("-j", type=int, default=multiprocessing.cpu_count(), help="Number of parallel workers (default: all CPUs)")

    args = parser.parse_args()
    process_directory(args.input_dir, args.output_dir, args.j)
