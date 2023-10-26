import os
from multiprocessing import Pool
from subprocess import Popen, PIPE
import shutil
import argparse



# circuits = ["clstm_like.large", "clstm_like.medium", "dla_like.medium", "proxy.7", "clstm_like.small", "tpu_like.large.ws", "tpu_like.large.os", \
# 			"bnn", "dla_like.small", "dnnweaver", "deepfreeze.style3", "lstm", "proxy.5", "bwave_like.fixed.large", "tpu_like.small.os", "conv_layer", "attention_layer", \
# 			"tpu_like.small.ws", "softmax", "tdarknet_like.large", "robot_rl", "bwave_like.fixed.small", "lenet", "eltwise_layer", "reduction_layer", "conv_layer_hls", "spmv"]
circuits = [
"clstm_like.medium",
"bnn",
"dla_like.medium",
"deepfreeze.style3",
"clstm_like.large"
]

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
	"tpu_like.small.os": "2_2",
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
	"tpu_like.small.os": "2_1",
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


def getArchFileName(circuit_name, arch_type):
	arch_name = ""
	if arch_type == "2D":
		arch_name = "aman_2d_coffe_" + circuit_2d_arch_map[circuit_name] + ".xml"
	elif arch_type == "partial3D":
		arch_name = "aman_3d_coffe_limited_" + circuit_3d_arch_map[circuit_name] + ".xml"
	else:
		assert arch_type == "full3D"
		arch_name = "aman_3d_coffe_" + circuit_3d_arch_map[circuit_name] + ".xml"
	return arch_name

def getRRGraphFileName(circuit_name, arch_type):
	arch_name = ""
	if arch_type == "2D":
		arch_name = "rr_graph_2d_" + circuit_2d_arch_map[circuit_name] + ".xml"
	elif arch_type == "partial3D":
		arch_name = "rr_graph_3d_limited_" + circuit_3d_arch_map[circuit_name] + ".xml"
	else:
		assert arch_type == "full3D"
		arch_name = "rr_graph_3d_" + circuit_3d_arch_map[circuit_name] + ".xml"
	return arch_name

def run_circuit(thread_arg):
	vpr_dir = thread_arg[0]
	input_file_dir = thread_arg[1]
	net_dir = thread_arg[2]
	circuit_name = thread_arg[3]
	run_type = thread_arg[4]
	limited_inter_connect = thread_arg[5]
	working_dir = thread_arg[6]
	print(f"start running {circuit_name} - path: {working_dir}")
	os.chdir(working_dir)
	os.system(f"rm -rf *")

	
	arch_dir = os.path.join(input_file_dir, getArchFileName(circuit_name, run_type))
	circuit_dir = os.path.join(net_dir, f"{circuit_name}.pre-vpr.blif")
	

	net_file_dir = os.path.join(net_dir, f"{circuit_name}.net")

	rr_graph_file_dir = os.path.join(input_file_dir, getRRGraphFileName(circuit_name, run_type))


	if (limited_inter_connect):
		process = Popen([vpr_dir, 
			arch_dir, 
			circuit_dir, 
			"--route_chan_width",
			"320",
			"--max_router_iterations",
			"200",
			"--read_rr_graph",
			rr_graph_file_dir,
			"--strict_checks",
			"off",
			"--verify_file_digests",
			"off",
			"--place_bounding_box_mode",
			"cube_bb",
			"--limited_inter_layer_connectivity",
			"true" if limited_inter_connect else "false",
			"--target_ext_pin_util", 
			"clb:1,0.6"],
			stdout=PIPE, 
			stderr=PIPE)
	else: 
		process = Popen([vpr_dir, 
			arch_dir, 
			circuit_dir, 
			"--route_chan_width",
			"320",
			"--max_router_iterations",
			"200",
			"--net_file",
			net_file_dir,
			"--read_rr_graph",
			rr_graph_file_dir,
			"--strict_checks",
			"off",
			"--verify_file_digests",
			"off",
			"--place_bounding_box_mode",
			"cube_bb",
			"--limited_inter_layer_connectivity",
			"true" if limited_inter_connect else "false",
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

	print(f"{circuit_name} is done!")


def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--input_file_dir", required=True, help="Directory that contains the input files (architecture, RR graph, etc.)")
	parser.add_argument("--net_file_dir", required=True, help="Directory that contains the net file")
	parser.add_argument("--less_dense_net_file_dir", required=True, help="Directory that contains the net file for 60 packed")
	parser.add_argument("--vpr_dir", required=True, help="VPR Executable Directory")

	args = parser.parse_args()
	return args



if __name__ == "__main__":

	args = getArgs()

	vpr_dir	 = args.vpr_dir
	input_file_dir = args.input_file_dir
	net_file_dir = args.net_file_dir
	less_dense_net_file_dir = args.less_dense_net_file_dir

	root_dir = os.path.abspath("./")

	print(f"Circuits: {circuits}")

	os.makedirs("run_dir_2d", exist_ok=True)
	working_dir = os.path.abspath("./run_dir_2d")
	thread_args = []
	for circuit in circuits:
		circuit_path = os.path.join(working_dir, f"{circuit}.v/common")
		os.makedirs(circuit_path, exist_ok=True)
		thread_args.append([vpr_dir, input_file_dir, net_file_dir, circuit, "2D", False, circuit_path])
		print(f"{circuit_path} is added")

	os.makedirs("run_dir_partial_3D", exist_ok=True)
	working_dir = os.path.abspath("./run_dir_partial_3D")
	for circuit in circuits:
		circuit_path = os.path.join(working_dir, f"{circuit}.v/common")
		os.makedirs(circuit_path, exist_ok=True)
		thread_args.append([vpr_dir, input_file_dir, less_dense_net_file_dir, circuit, "partial3D", True, circuit_path])
		print(f"{circuit_path} is added")

	os.makedirs("run_dir_full_3D", exist_ok=True)
	working_dir = os.path.abspath("./run_dir_full_3D")
	for circuit in circuits:
		circuit_path = os.path.join(working_dir, f"{circuit}.v/common")
		os.makedirs(circuit_path, exist_ok=True)
		thread_args.append([vpr_dir, input_file_dir, net_file_dir, circuit, "full3D", False, circuit_path])
		print(f"{circuit_path} is added")

	pool = Pool(30)
	pool.map(run_circuit, thread_args)
	pool.close()

	print("Done with all circuits!")


