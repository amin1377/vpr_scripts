import os
from multiprocessing import Pool
from subprocess import Popen, PIPE
import shutil
import subprocess
import argparse
import re
import concurrent.futures

architecture_name = "3d_SB_inter_die_stratixiv_arch.timing.xml"
edge_removal_rates = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9]
mux_removal_rates = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9]

def parse_vtr_run(thread_args):
    task_dir, parse_script_path, run_dir_num, parse_result_file_name = thread_args
    run_dir = os.path.join(task_dir, f"run{run_dir_num:03d}")
    print(f"Parsing run {run_dir}")

    subprocess.run(["python3", parse_script_path, task_dir, "-run", f"{run_dir_num}"], check=True)
    parse_result_dir = os.path.join(task_dir, f"run{run_dir_num:03d}", "parse_results.txt")
    if not os.path.exists(parse_result_dir):
        print(f"Parse result {parse_result_dir} does not exist")
        return
    os.rename(parse_result_dir, os.path.join(task_dir, run_dir, parse_result_file_name))

def get_args():
    parser = argparse.ArgumentParser(description="Copy and rename circuit files.")
    parser.add_argument("--vtr_root_dir", help="Path to the VTR root directory")
    parser.add_argument("--task_dir", help="Path to directory of runs")
    parser.add_argument("--num_threads", help="Number of threads to use", type=int, default=1)
    return parser.parse_args()

def main():
    args = get_args()

    parse_script_path = os.path.join(args.vtr_root_dir, "vtr_flow/scripts/python_libs/vtr/parse_vtr_task.py")
    if not os.path.exists(parse_script_path):
        print(f"Parse script {parse_script_path} does not exist")
        return

    thread_args = []
    run_dir_num = 2
    for edge_removal_rate in edge_removal_rates:
        for mux_removal_rate in mux_removal_rates:
            parse_result_file_name = f"parse_result_{int(edge_removal_rate * 100)}_{int(mux_removal_rate * 100)}.txt"
            thread_args.append((args.task_dir, parse_script_path, run_dir_num, parse_result_file_name))
            run_dir_num += 1

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.num_threads) as executor:
        executor.map(parse_vtr_run, thread_args)
    print("Done!")


if __name__ == "__main__":
    main()