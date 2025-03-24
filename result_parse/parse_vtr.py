import os
from multiprocessing import Pool
from subprocess import Popen, PIPE
import shutil
import subprocess
import argparse
import re

architecture_name = "3d_SB_inter_die_stratixiv_arch.timing.xml"
edge_removal_rates = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9]
mux_removal_rates = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9]



def get_next_run_dir_name(parent_dir):
    """
    Finds the next available 'runXXX' directory name in the given parent directory.
    
    Args:
        parent_dir (str): Path to the parent directory.
        
    Returns:
        str: The next 'runXXX' directory name (e.g., 'run005' if 'run004' exists).
    """
    max_run_number = -1  # Initialize with a negative value in case no 'runXXX' exists
    run_pattern = re.compile(r"^run(\d+)$")  # Regex to match "runXXX"

    for subdir in os.listdir(parent_dir):
        match = run_pattern.match(subdir)
        if match:
            run_number = int(match.group(1))  # Extract numeric part
            max_run_number = max(max_run_number, run_number)

    next_run_number = max_run_number + 1
    return f"run{next_run_number:03d}"  # Format as 'runXXX' (e.g., run005)

def main():
    parser = argparse.ArgumentParser(description="Copy and rename circuit files.")
    parser.add_argument("--vtr_root_dir", help="Path to the VTR root directory")
    parser.add_argument("--task_dir", help="Path to directory of runs")
    args = parser.parse_args()

    run_dir_num = 2
    parse_script_path = os.path.join(args.vtr_root_dir, "vtr_flow/scripts/python_libs/vtr/parse_vtr_task.py")
    if not os.path.exists(parse_script_path):
        print(f"Parse script {parse_script_path} does not exist")
        return
    for edge_removal_rate in edge_removal_rates:
        for mux_removal_rate in mux_removal_rates:
            run_dir = os.path.join(args.task_dir, f"run{run_dir_num:03d}")
            new_run_dir_name = get_next_run_dir_name(args.task_dir)
            symlink_path = os.path.join(args.task_dir, new_run_dir_name)
            os.symlink(run_dir, symlink_path)
            print(f"Symlink created: {run_dir} → {symlink_path}")
            subprocess.run(["python3", parse_script_path, args.task_dir], check=True)
            parse_result_dir = os.path.join(args.task_dir, new_run_dir_name, "parse_results.txt")
            if not os.path.exists(parse_result_dir):
                print(f"Parse result {parse_result_dir} does not exist")
                return
            os.rename(parse_result_dir, os.path.join(args.task_dir, new_run_dir_name, f"parse_result_{int(edge_removal_rate * 100)}_{int(mux_removal_rate * 100)}.txt"))
            os.unlink(symlink_path)
            print(f"Removed symlink: {symlink_path}")
            run_dir_num += 1
    print("Done!")


if __name__ == "__main__":
    main()


