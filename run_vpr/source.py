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

def getCircuits(reference_dir):
	return os.listdir(reference_dir)

def run_circuit(thread_arg):
	ref_dir = thread_arg[0]
	working_dir = os.path.join(thread_arg[1], "common")
	circuit_name = thread_arg[2]
	print(f"start running {circuit_name} - path: {working_dir}")
	os.chdir(working_dir)
	os.system(f"rm -rf *")

	
	vpr_dir = "/home/mohagh18/vtr-verilog-to-routing/vpr/vpr"
	arch_dir = "/home/mohagh18/vtr-verilog-to-routing/vtr_flow/arch/titan/stratixiv_arch.timing.xml"
	circuit_dir = f"/home/mohagh18/vtr-verilog-to-routing/vtr_flow/benchmarks/titan_blif/{circuit_name}"
	
	sdc_file_dir = "/home/mohagh18/vtr-verilog-to-routing/vtr_flow/benchmarks/titan_blif"
	sdc_file_name = circuit_name[:-5]+".sdc"
	sdc_file_dir = os.path.join(sdc_file_dir, sdc_file_name)

	place_file_name = circuit_name[:-5]+".place"
	place_file_dir = os.path.join(ref_dir, circuit_name, "common", place_file_name)

	net_file_name = circuit_name[:-5]+".net"
	net_file_dir = os.path.join(ref_dir, circuit_name, "common", net_file_name)

	first_iter_pres_fac = thread_arg[3]

	# rr_graph_file_name = "rr_graph.xml"
	# rr_graph_file_dir = os.path.join(ref_dir, circuit_name, "common", rr_graph_file_name)

	copyFileToCurrDir(sdc_file_dir, place_file_dir, net_file_dir)
	# copyFileToCurrDir(net_file_dir, rr_graph_file_dir, sdc_file_dir)

	process = Popen([vpr_dir, 
		arch_dir, 
		circuit_dir, 
		"--route_chan_width",
		"300", 
		"--max_router_iterations",
		"400",
		"--router_lookahead",
		"map", 
		"--initial_pres_fac",
		"1.0",
		"--router_profiler_astar_fac",
		"1.5",
		"--seed",
		"3",
		"--flat_routing",
		"false",
		"--first_iter_pres_fac",
		first_iter_pres_fac,
		"--sdc_file",
		sdc_file_name,
		"--net_file",
		net_file_name,
		"--place_file",
		place_file_name,
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
	reference_dir = "/home/mohagh18/vtr-verilog-to-routing/vtr_flow/tasks/regression_tests/vtr_reg_nightly_test2/titan_quick_qor/run002/stratixiv_arch.timing.xml"
	circuits = getCircuits(reference_dir)
	print(f"Circuits: {circuits}")
	first_iter_pres_fac_vec = ["0.1", "0.2", "0.3", "0.4", "0.5"]
	os.system("rm -rf pres_fac_*")

	for first_iter_pres_fac in first_iter_pres_fac_vec:
		os.makedirs(f"pres_fac_{first_iter_pres_fac}/stratixiv_arch.timing.xml")
		working_dir = f"/home/mohagh18/Desktop/different_initial_pres_fac/pres_fac_{first_iter_pres_fac}/stratixiv_arch.timing.xml"
		
		os.system(f"rm -rf {os.path.join(working_dir, '')}*")
		thread_args = []
		for circuit in circuits:
			circuit_path = os.path.join(working_dir, circuit)
			os.mkdir(circuit_path)
			os.mkdir(f"{circuit_path}/common")
			thread_args.append([reference_dir, circuit_path, circuit, first_iter_pres_fac])
			print(f"{circuit_path} is added")

		pool = Pool(20)
		pool.map(run_circuit, thread_args)
		pool.close()
		
		print(f"Done with all circuits! first_iter_pres_fac : {first_iter_pres_fac}")


