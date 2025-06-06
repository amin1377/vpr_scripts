import os
from multiprocessing import Pool
from subprocess import Popen, PIPE
import shutil
import subprocess
import argparse
import re

circuits = ["clstm_like.large", "clstm_like.medium", "dla_like.medium", "proxy.7", "clstm_like.small", "tpu_like.large.ws", "tpu_like.large.os", \
			"bnn", "dla_like.small", "dnnweaver", "deepfreeze.style3", "lstm", "proxy.5", "bwave_like.fixed.large", "conv_layer", "attention_layer", \
			"tpu_like.small.ws", "softmax", "tdarknet_like.large", "robot_rl", "bwave_like.fixed.small", "lenet", "eltwise_layer", "reduction_layer", "conv_layer_hls", "spmv"]


circuit_2d_arch_map = {
	"clstm_like.large": "5_5",
	"clstm_like.medium": "4_4",
	"dla_like.medium": "4_4",
	"proxy.7": "4_4",
	"clstm_like.small": "3_3",
	"tpu_like.large.ws": "4_4",
	"tpu_like.large.os": "4_4",
	"bnn": "3_3",
	"dla_like.small": "3_3",
	"dnnweaver": "4_4",
	"deepfreeze.style3": "3_3",
	"lstm": "3_3",
	"proxy.5": "3_3",
	"bwave_like.fixed.large": "3_3",
	"conv_layer": "2_2",
	"attention_layer": "2_2",
	"tpu_like.small.ws": "1_1",
	"softmax": "2_2",
	"tdarknet_like.large": "3_3",
	"robot_rl": "1_1",
	"bwave_like.fixed.small": "2_2",
	"lenet": "2_2",
	"eltwise_layer": "1_1",
	"reduction_layer": "1_1",
	"conv_layer_hls": "3_3",
	"spmv": "2_2"
}

circuit_3d_arch_map = {
	"clstm_like.large": "4_4",
	"clstm_like.medium": "4_2",
	"dla_like.medium": "4_2",
	"proxy.7": "4_2",
	"clstm_like.small": "2_2",
	"tpu_like.large.ws": "4_2",
	"tpu_like.large.os": "4_2",
	"bnn": "2_2",
	"dla_like.small": "2_2",
	"dnnweaver": "4_2",
	"deepfreeze.style3": "2_2",
	"lstm": "2_2",
	"proxy.5": "2_2",
	"bwave_like.fixed.large": "2_2",
	"conv_layer": "2_1",
	"attention_layer": "2_1",
	"tpu_like.small.ws": "1_1",
	"softmax": "2_1",
	"tdarknet_like.large": "2_2",
	"robot_rl": "1_1",
	"bwave_like.fixed.small": "2_1",
	"lenet": "2_1",
	"eltwise_layer": "1_1",
	"reduction_layer": "1_1",
	"conv_layer_hls": "2_2",
	"spmv": "2_1"
}

def run_circuit(thread_arg):
    vpr_dir = thread_arg[0]
    circuit_name = thread_arg[1]
    arch_dir = thread_arg[2]
    blif_file_dir = thread_arg[3]
    net_file_dir = thread_arg[4]
    circuit_dir = thread_arg[5]
    multi_die = thread_arg[6]

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
        

    os.symlink(arch_dir, os.path.basename(arch_dir))
    os.symlink(blif_file_dir, os.path.basename(blif_file_dir))
    os.symlink(net_file_dir, os.path.basename(net_file_dir))

    command = [vpr_dir,
                arch_dir,
                blif_file_dir,
                "--route_chan_width",
                "320",
                "--max_router_iterations",
                "400",
                "--strict_checks",
                "off",
                "--verify_file_digests",
                "off",
                "--write_rr_graph",
                f"rr_graph_{circuit_name}.xml"]
    if multi_die:
        command.append("--device")
        command.append(f"sector_{circuit_3d_arch_map[circuit_name]}")
        command.append("--custom_3d_sb_fanin_fanout")
        command.append("60")
    else:
        command.append("--device")
        command.append(f"sector_{circuit_2d_arch_map[circuit_name]}")

    process = Popen(command,
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

def main():
    parser = argparse.ArgumentParser(description="Copy and rename circuit files.")
    parser.add_argument("--vtr_root_dir", help="Path to the VTR root directory")
    parser.add_argument("--input_dir", help="Path to the input directory")
    parser.add_argument("--output_dir", help="Path to the output directory")
    parser.add_argument("--architecture_name", help="Architecture name")
    parser.add_argument("--multi_die", help="Multi die", action="store_true")
    parser.add_argument("-j", help="Number of threads to use")
    args = parser.parse_args()
    number_of_threads = int(args.j)
    architecture_name = args.architecture_name
    multi_die = args.multi_die
    vpr_dir = os.path.join(args.vtr_root_dir, "vpr", "vpr")
    if not os.path.exists(vpr_dir):
        print(f"VPR executable {vpr_dir} does not exist")
        return

    thread_args = []

    run_dir_name = f"run001"
    run_dir_path = os.path.join(args.output_dir, run_dir_name, architecture_name)
    for circuit in circuits:
        circuit_dir = os.path.join(run_dir_path, f"{circuit}.blif", "common")
        os.makedirs(circuit_dir, exist_ok=True)
        net_file_dir = os.path.join(args.input_dir, f"{circuit}.net")
        arch_file_dir = os.path.join(args.input_dir, architecture_name)
        blif_file_dir = os.path.join(args.input_dir, f"{circuit}.pre-vpr.blif")
        thread_args.append((vpr_dir, circuit, arch_file_dir, blif_file_dir, net_file_dir, circuit_dir, multi_die))
    
    pool = Pool(number_of_threads)
    pool.map(run_circuit, thread_args)
    pool.close()

    print("Done with all circuits!")


if __name__ == "__main__":
    main()


