import os
import argparse
import matplotlib.pyplot as plt

def checkHeader(header_line):
	header_is_correct = True
	header = header_line.split("\t")
	header_is_correct &= (header[0] == "Net id")
	header_is_correct &=  ((header[-1] == "Expected wirelength") or (header[-1] == "Expected delay"))
	if len(header) > 2:
		header_is_correct &= (len(header) == 3)
		header_is_correct &= (header[1] == "Sink id")

	return header_is_correct


def getSortedDictByKey(input_dict):
	sorted_dict = {k: input_dict[k] for k in sorted(input_dict)}
	return sorted_dict

def getSortedDictByVal(input_dict):
	sorted_dict = dict(sorted(input_dict.items(), key=lambda item: item[1]))
	return sorted_dict

def getNetValPair(file_lines):

	header = None
	net_val_pair = {}
	for line_num, line in enumerate(file_lines):
		if line_num == 0:
			header = line
			assert checkHeader(line)
		else:
			split_line = line.split("\t")
			net_id = None
			sink_id = None
			val = None
			net_id = int(split_line[0])
			if len(split_line) == 2:
				val = float(split_line[1])
			else:
				assert len(split_line) == 3
				sink_id = int(split_line[1])
				val = float(split_line[2])

			if net_id in net_val_pair:
				assert sink_id
				net_val_pair[net_id][sink_id] = val
			else:
				if sink_id:
					net_val_pair[net_id] = {sink_id: val}
				else:
					net_val_pair[net_id] = val

	return header, net_val_pair






def getCircuitInfo(act_file_name, est_file_name, out_file_name):
	act_file_lines = None
	est_file_lines = None

	ratio_arr = {}

	with open(act_file_name, 'r') as act_file:
		act_file_lines = [line.strip() for line in act_file.readlines()]

	with open(est_file_name, 'r') as est_file:
		est_file_lines = [line.strip() for line in est_file.readlines()]

	header, act_file_net_val_pair = getNetValPair(act_file_lines)
	act_file_net_val_pair = getSortedDictByKey(act_file_net_val_pair)

	_, est_file_net_val_pair = getNetValPair(est_file_lines)
	est_file_net_val_pair = getSortedDictByKey(est_file_net_val_pair)

	assert len(act_file_net_val_pair) == len(est_file_net_val_pair)

	with open(out_file_name, 'w') as out_file:
		out_file.write(f"{header}\n")
		include_sink_num = (len(header.split("\t")) == 3) 
		assert include_sink_num or (len(header.split("\t")) == 2)
		for net_id in act_file_net_val_pair:
			ratio_arr[net_id] = {}
			assert net_id in est_file_net_val_pair
			act_val = act_file_net_val_pair[net_id]
			est_val = est_file_net_val_pair[net_id]
			
			assert isinstance(act_val, dict) == isinstance(est_val, dict) 

			if isinstance(act_val, dict):
				assert len(act_val) == len(est_val)
				act_val = getSortedDictByKey(act_val)
				est_val = getSortedDictByKey(est_val)
				for sink_num in act_val:
					if act_val[sink_num] == 0.:
						ratio = -1
					else:
						ratio = ((est_val[sink_num] - act_val[sink_num]) / act_val[sink_num])
					ratio_arr[net_id][sink_num] = ratio
					out_file.write(f"{net_id}\t{sink_num}\t{ratio:.2f}\n")

			else:
				if act_val == 0.:
					ratio = -1
				else:
					ratio = ((est_val - act_val) / act_val)
				ratio_arr[net_id] = ratio
				out_file.write(f"{net_id}\t{ratio:.2f}\n")

	return ratio_arr

def getNetInfo(net_fan_out_dir):
	net_info_lines = None
	with open(net_fan_out_dir, 'r') as net_info_file:
		net_info_lines = [line.strip() for line in net_info_file.readlines()]

	net_sink_map = {}
	for line_num, line in enumerate(net_info_lines):
		if line_num == 0:
			header = line.split("\t")
			assert header[0] == "Net id"
			assert header[1] == "Num Sinks"
		else:
			net_id = int(line.split("\t")[0])
			num_sinks = int(line.split("\t")[1])
			assert not net_id in net_sink_map
			net_sink_map[net_id] = num_sinks

	return net_sink_map

def unionFanOut(circuits_fan_out):
	fan_outs = set()
	for circuit_name in circuits_fan_out:
		for net_num in circuits_fan_out[circuit_name]:
			fan_outs.add(int(circuits_fan_out[circuit_name][net_num]))

	fan_outs = sorted(fan_outs)

	return fan_outs


def main(task_dir):
	sub_dirs = os.listdir(task_dir)

	circuit_wl_map = {}
	circuit_td_map = {}
	circuit_net_info = {}
	wl_fan_out_dict = {}
	print(f"Circuits: {sub_dirs}")

	for sub_dir in sub_dirs:
		circuit_dir = os.path.join(task_dir, sub_dir, "common")
		
		place_wl_act_dir = os.path.join(circuit_dir, "route_wl.txt")
		assert os.path.isfile(place_wl_act_dir)
		place_wl_est_dir = os.path.join(circuit_dir, "place_wl_est.txt")
		assert os.path.isfile(place_wl_est_dir)
		out_wl_ratio_file_name = os.path.join(circuit_dir, "wl_ratio.txt")

		circuit_wl_map[sub_dir] = getCircuitInfo(place_wl_act_dir, place_wl_est_dir, out_wl_ratio_file_name)

		place_td_act_dir = os.path.join(circuit_dir, "route_td.txt")
		assert os.path.isfile(place_td_act_dir)
		place_td_est_dir = os.path.join(circuit_dir, "place_td_est.txt")
		assert os.path.isfile(place_td_est_dir)
		out_td_ratio_file_name = os.path.join(circuit_dir, "td_ratio.txt")

		circuit_td_map[sub_dir] = getCircuitInfo(place_td_act_dir, place_td_est_dir, out_td_ratio_file_name)

		circuit_fan_out_dir = os.path.join(circuit_dir, "net_info.txt")
		assert os.path.isfile(circuit_fan_out_dir)

		circuit_net_info[sub_dir] = getNetInfo(circuit_fan_out_dir)


	union_fan_out = unionFanOut(circuit_net_info)
	print(union_fan_out)

	fan_out_wl_cnt_map = {key: 0 for key in union_fan_out}
	fan_out_wl_ratio_map = {key: 0. for key in union_fan_out}

	for sub_dir in circuit_wl_map:
		for net_num in circuit_wl_map[sub_dir]:
			assert sub_dir in circuit_net_info
			assert sub_dir in circuit_wl_map
			assert net_num in circuit_net_info[sub_dir]
			assert net_num in circuit_wl_map[sub_dir]

			net_fan_out = circuit_net_info[sub_dir][net_num]
			ratio = circuit_wl_map[sub_dir][net_num]
			if ratio >= 0:
				assert ratio <= 1
				fan_out_wl_cnt_map[net_fan_out] += 1
				fan_out_wl_ratio_map[net_fan_out] += abs(ratio)


	for fan_out in union_fan_out:
		ratio = fan_out_wl_ratio_map[fan_out]
		cnt = fan_out_wl_cnt_map[fan_out]
		if not cnt == 0:
			fan_out_wl_ratio_map[fan_out] = ratio/cnt
		else:
			fan_out_wl_ratio_map.pop(fan_out)
			fan_out_wl_cnt_map.pop(fan_out)

	keys = list(fan_out_wl_ratio_map.keys())
	values = list(fan_out_wl_ratio_map.values())
	dist_vals = list(fan_out_wl_cnt_map.values())

	fig = plt.figure()

	val_sub_plot = fig.add_subplot(1, 2, 1)
	val_sub_plot.plot(keys, values, marker='o', color='b', label='Data')
	val_sub_plot.set_xlabel('Keys')
	val_sub_plot.set_ylabel('Values')
	val_sub_plot.set_title('Line Plot of Dictionary Values')

	dist_sub_plot = fig.add_subplot(1, 2, 2)
	dist_sub_plot.plot(keys, dist_vals, marker='o', color='b', label='Data')
	dist_sub_plot.set_xlabel('Keys')
	dist_sub_plot.set_ylabel('Values')
	dist_sub_plot.set_title('Line Plot of Dictionary Values')

	plt.tight_layout()
	plt.show()





def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--task_dir", required=True, help="File that contains the actual results")

	args = parser.parse_args()
	return args

if __name__ == "__main__":
	args = getArgs()
	main(args.task_dir)