import os
from multiprocessing import Pool
from subprocess import Popen, PIPE
import shutil
import subprocess
import argparse
import re

architecture_name = "3d_SB_inter_die_stratixiv_arch.timing.xml"
circuits = ["carpat_stratixiv_arch_timing", "CH_DFSIN_stratixiv_arch_timing", "CHERI_stratixiv_arch_timing", "fir_cascade_stratixiv_arch_timing", "jacobi_stratixiv_arch_timing", "JPEG_stratixiv_arch_timing", \
            "leon2_stratixiv_arch_timing", "leon3mp_stratixiv_arch_timing", "MCML_stratixiv_arch_timing", "MMM_stratixiv_arch_timing", "radar20_stratixiv_arch_timing", "random_stratixiv_arch_timing", \
            "Reed_Solomon_stratixiv_arch_timing", "smithwaterman_stratixiv_arch_timing", "stap_steering_stratixiv_arch_timing", "sudoku_check_stratixiv_arch_timing", "SURF_desc_stratixiv_arch_timing", \
            "ucsb_152_tap_fir_stratixiv_arch_timing", "uoft_raytracer_stratixiv_arch_timing", "picosoc_stratixiv_arch_timing", "murax_stratixiv_arch_timing", \
            "EKF-SLAM_Jacobians_stratixiv_arch_timing"]
edge_removal_rates = [0.05, 0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98]
edge_mux_removal_rates = [0.50, 0.65, 0.80]
mux_removal_rates = [0.05, 0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98]


def run_circuit(thread_arg):
    vpr_dir = thread_arg[0]
    arch_dir = thread_arg[1]
    blif_file_dir = thread_arg[2]
    net_file_dir = thread_arg[3]
    rr_graph_file_dir = thread_arg[4]
    sdc_file_dir = thread_arg[5]
    circuit_dir = thread_arg[6]

    os.chdir(circuit_dir)
    print(f"Running in {circuit_dir}")

    # enusre input files exist
    if not os.path.exists(arch_dir):
        print(f"Architecture file {arch_dir} does not exist")
        return
    if not os.path.exists(blif_file_dir):
        print(f"BLIF file {blif_file_dir} does not exist")
        return
    if not os.path.exists(net_file_dir):
        print(f"Net file {net_file_dir} does not exist")
        return
    if not os.path.exists(rr_graph_file_dir):
        print(f"RR graph file {rr_graph_file_dir} does not exist")
        return
    if not os.path.exists(sdc_file_dir):
        print(f"SDC file {sdc_file_dir} does not exist")
        return
        

    os.symlink(arch_dir, os.path.basename(arch_dir))
    os.symlink(blif_file_dir, os.path.basename(blif_file_dir))
    os.symlink(net_file_dir, os.path.basename(net_file_dir))
    os.symlink(rr_graph_file_dir, os.path.basename(rr_graph_file_dir))
    os.symlink(sdc_file_dir, os.path.basename(sdc_file_dir))    


    process = Popen([vpr_dir, 
        os.path.basename(arch_dir), 
        os.path.basename(blif_file_dir), 
        "--route_chan_width",
        "300",
        "--max_router_iterations",
        "400",
        "--custom_3d_sb_fanin_fanout",
        "60",
        "--router_lookahead",
        "map",
        "--net_file",
        os.path.basename(net_file_dir),
        "--read_rr_graph",
        os.path.basename(rr_graph_file_dir),
        "--sdc_file",
        os.path.basename(sdc_file_dir),
        "--place",
        "--route",
        "--analysis"],
        stdout=PIPE, 
        stderr=PIPE)
    stdout, stderr = process.communicate()
    
    f = open("vpr.out", "w")
    f.write(stdout.decode())
    f.close()

    f = open("vpr_err.out", "w")
    f.write(stderr.decode())
    f.close()

    print(f"{circuit_dir} is done!")


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
    parser.add_argument("--input_dir", help="Path to the input directory")
    parser.add_argument("--output_dir", help="Path to the output directory")
    parser.add_argument("-j", help="Number of threads to use")
    args = parser.parse_args()
    number_of_threads = int(args.j)

    vpr_dir = os.path.join(args.vtr_root_dir, "vpr", "vpr")
    if not os.path.exists(vpr_dir):
        print(f"VPR executable {vpr_dir} does not exist")
        return

    thread_args = []
    edge_removeal_run_dir_names = []
    edge_mux_removal_run_dir_names = []

    for edge_removal_rate in edge_removal_rates:
        run_dir_name = get_next_run_dir_name(args.output_dir)
        run_dir_path = os.path.join(args.output_dir, run_dir_name, architecture_name)
        os.makedirs(run_dir_path, exist_ok=True)
        edge_removeal_run_dir_names.append([run_dir_path, edge_removal_rate])
        for circuit in circuits:
            circuit_dir = os.path.join(run_dir_path, f"{circuit}.blif", "common")
            os.makedirs(circuit_dir, exist_ok=True)
            rr_graph_file_dir = os.path.join(args.input_dir, f"rr_graph_{circuit}_{int(edge_removal_rate * 100)}.xml")
            net_file_dir = os.path.join(args.input_dir, f"{circuit}.net")
            sdc_file_dir = os.path.join(args.input_dir, f"{circuit}.sdc")
            arch_file_dir = os.path.join(args.input_dir, architecture_name)
            blif_file_dir = os.path.join(args.input_dir, f"{circuit}.blif")
            thread_args.append((args.vpr_dir, arch_file_dir, blif_file_dir, net_file_dir, rr_graph_file_dir, sdc_file_dir, circuit_dir))
    
    for edge_mux_removal_rate in edge_mux_removal_rates:
        for mux_removal_rate in mux_removal_rates:
            run_dir_name = get_next_run_dir_name(args.output_dir)
            run_dir_path = os.path.join(args.output_dir, run_dir_name, architecture_name)
            os.makedirs(run_dir_path, exist_ok=True)
            edge_mux_removal_run_dir_names.append([run_dir_path, edge_mux_removal_rate, mux_removal_rate])
            for circuit in circuits:
                circuit_dir = os.path.join(run_dir_path, f"{circuit}.blif", "common")
                os.makedirs(circuit_dir, exist_ok=True)
                rr_graph_file_dir = os.path.join(args.input_dir, f"rr_graph_{circuit}_{int(edge_mux_removal_rate * 100)}_mux_{int(mux_removal_rate * 100)}.xml")
                net_file_dir = os.path.join(args.input_dir, f"{circuit}.net")
                sdc_file_dir = os.path.join(args.input_dir, f"{circuit}.sdc")
                arch_file_dir = os.path.join(args.input_dir, architecture_name)
                blif_file_dir = os.path.join(args.input_dir, f"{circuit}.blif")
                thread_args.append((args.vpr_dir, arch_file_dir, blif_file_dir, net_file_dir, rr_graph_file_dir, sdc_file_dir, circuit_dir))
    
    pool = Pool(number_of_threads)
    pool.map(run_circuit, thread_args)
    pool.close()

    parse_script_path = os.path.join(args.vtr_root_dir, "vtr_flow/scripts/python_libs/vtr/parse_vtr_task.py")
    if not os.path.exists(parse_script_path):
        print(f"Parse script {parse_script_path} does not exist")
        return

    for run_dir, edge_removal_rate in edge_removeal_run_dir_names:
        new_run_dir_name = get_next_run_dir_name(args.output_dir)
        symlink_path = os.path.join(args.output_dir, new_run_dir_name)
        os.symlink(run_dir, symlink_path)
        print(f"Symlink created: {run_dir} → {symlink_path}")
        subprocess.run(["python3", parse_script_path, args.output_dir], check=True)
        parse_result_dir = os.path.join(args.output_dir, new_run_dir_name, "parse_result.txt")
        if not os.path.exists(parse_result_dir):
            print(f"Parse result {parse_result_dir} does not exist")
            return
        os.rename(parse_result_dir, os.path.join(args.output_dir, new_run_dir_name, f"parse_result_{int(edge_removal_rate * 100)}.txt"))
        os.unlink(symlink_path)
        print(f"Removed symlink: {symlink_path}")
    
    for run_dir, edge_mux_removal_rate, mux_removal_rate in edge_mux_removal_run_dir_names:
        new_run_dir_name = get_next_run_dir_name(args.output_dir)
        symlink_path = os.path.join(args.output_dir, new_run_dir_name)
        os.symlink(run_dir, symlink_path)
        print(f"Symlink created: {run_dir} → {symlink_path}")
        subprocess.run(["python3", parse_script_path, args.output_dir], check=True)
        parse_result_dir = os.path.join(args.output_dir, new_run_dir_name, "parse_result.txt")
        if not os.path.exists(parse_result_dir):
            print(f"Parse result {parse_result_dir} does not exist")
            return
        os.rename(parse_result_dir, os.path.join(args.output_dir, new_run_dir_name, f"parse_result_{int(edge_mux_removal_rate * 100)}_mux_{int(mux_removal_rate * 100)}.txt"))
        os.unlink(symlink_path)
        print(f"Removed symlink: {symlink_path}")
        






    print("Done with all circuits!")


if __name__ == "__main__":
    main()


