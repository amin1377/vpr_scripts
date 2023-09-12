import os
from multiprocessing import Pool
from subprocess import Popen, PIPE
import shutil

def copyFileToCurrDir(*files):
	for f in files:
		if os.path.isfile(f):
			shutil.copy(f, "./")
		else:
			print(f"Couldn't find {f}!")
			exit(1)

def getCircuits(ref_dir):
	# return ["attention_layer.v", "bwave_like.float.large.v", "clstm_like.small.v", "deepfreeze.style1.sv", "dla_like.medium.v", "gemm_layer.v", "lstm.v", "proxy.4.v", "proxy.8.v", \
	# "softmax.v", "test.v", "tpu_like.small.ws.v", "bnn.v", "deepfreeze.style2.sv", "dla_like.small.v", "proxy.1.v", "proxy.5.v", "spmv.v", "tpu_like.large.os.v", \
	# "bwave_like.fixed.large.v", "clstm_like.large.v", "conv_layer_hls.v", "deepfreeze.style3.sv", "dnnweaver.v", "proxy.2.v", "proxy.6.v", "reduction_layer.v", \
	# "tdarknet_like.large.v", "tpu_like.large.ws.v", "bwave_like.fixed.small.v", "clstm_like.medium.v", "conv_layer.v", "dla_like.large.v", "eltwise_layer.v", \
	# "lenet.v", "proxy.3.v", "proxy.7.v", "robot_rl.v", "tdarknet_like.small.v", "tpu_like.small.os.v"]
    # Get a list of all files in the directory
    all_files = os.listdir(ref_dir)

    # Separate the files with "*.pre-vpr.blif" and ".net" patterns
    pre_vpr_files = set()
    net_files = set()

    for file in all_files:
        if file.endswith(".pre-vpr.blif"):
            pre_vpr_files.add(file[:-len(".pre-vpr.blif")])
        elif file.endswith(".net"):
            net_files.add(file[:-len(".net")])

    # Get the common names between the two sets
    common_names = pre_vpr_files.intersection(net_files)
    return common_names

def run_circuit(thread_arg):
	ref_dir = thread_arg[0]
	working_dir = thread_arg[1]
	circuit_name = thread_arg[2]
	print(f"start running {circuit_name} - path: {working_dir}")
	os.chdir(working_dir)
	os.system(f"rm -rf *")

	
	vpr_dir = "/home/mohagh18/Desktop/vtr-verilog-to-routing/vpr/vpr"
	arch_dir = os.path.join(ref_dir, "aman_3d_coffe.xml")
	circuit_dir = os.path.join(ref_dir, f"{circuit_name}.pre-vpr.blif")
	

	net_file_dir = os.path.join(ref_dir, f"{circuit_name}.net")

	rr_graph_file_dir = os.path.join(ref_dir, "rr_graph.xml")


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




if __name__ == "__main__":
	reference_dir = "/home/mohagh18/run_koios/ref_dir_3d"
	circuits = getCircuits(reference_dir)
	print(f"Circuits: {circuits}")
	working_dir = "/home/mohagh18/run_koios/run001/aman_3d_coffe.xml"
	os.system(f"rm -rf {os.path.join(working_dir, '')}*")
	thread_args = []
	for circuit in circuits:
		circuit_path = os.path.join(working_dir, f"{circuit}.v/common")
		os.makedirs(circuit_path, exist_ok=True)
		thread_args.append([reference_dir, circuit_path, circuit])
		print(f"{circuit_path} is added")

	pool = Pool(4)
	pool.map(run_circuit, thread_args)
	pool.close()

	print("Done with all circuits!")


