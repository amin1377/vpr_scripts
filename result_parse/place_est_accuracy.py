import os
import argparse
import matplotlib.pyplot as plt
import numpy as np
import matplotlib

def checkHeader(header_line):
	header_is_correct = True
	header = header_line.split("\t")
	header_is_correct &= (header[0] == "Net id")
	header_is_correct &=  ((header[-1] == "Expected wirelength") or (header[-1] == "Expected delay"))
	if len(header) == 5:
		header_is_correct &= (header[1] == "Sink id")
		header_is_correct &= (header[2] == "dx")
		header_is_correct &= (header[3] == "dy")
	else:
		header_is_correct &= (len(header) == 2)

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
			dx = None
			dy = None
			val = None
			net_id = int(split_line[0])
			if len(split_line) == 2:
				val = float(split_line[1])
			else:
				assert len(split_line) == 5
				sink_id = int(split_line[1])
				dx = int(split_line[2])
				dy = int(split_line[3])
				val = float(split_line[4])

			if net_id in net_val_pair:
				assert sink_id != None
				assert dx != None
				assert dy != None
				net_val_pair[net_id][(sink_id,dx,dy)] = val
			else:
				if sink_id:
					assert dx != None
					assert dy != None
					net_val_pair[net_id] = {(sink_id,dx,dy): val}
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
		include_sink_num = (len(header.split("\t")) == 5) 
		assert include_sink_num or (len(header.split("\t")) == 2)
		for net_id in act_file_net_val_pair:
			if not net_id in ratio_arr:
				ratio_arr[net_id] = {}
			assert net_id in est_file_net_val_pair
			act_val = act_file_net_val_pair[net_id]
			est_val = est_file_net_val_pair[net_id]
			
			assert isinstance(act_val, dict) == isinstance(est_val, dict) 

			if isinstance(act_val, dict):
				assert len(act_val) == len(est_val)
				act_val = getSortedDictByKey(act_val)
				est_val = getSortedDictByKey(est_val)
				for key in act_val:
					sink_num = key[0]
					dx = key[1]
					dy = key[2]
					if act_val[key] == 0.:
						continue
					ratio = ((est_val[key] - act_val[key]) / act_val[key])
					ratio_arr[net_id][key] = abs(ratio)
					out_file.write(f"{net_id}\t{sink_num}\t{dx}\t{dy}\t{ratio:.2f}\n")

			else:
				if act_val == 0.:
					continue
				else:
					ratio = ((est_val - act_val) / act_val)
				ratio_arr[net_id] = abs(ratio)
				out_file.write(f"{net_id}\t{ratio:.2f}\n")

	return act_file_net_val_pair, est_file_net_val_pair, ratio_arr

def getWlPercentage(act_file_name, est_file_name):
	act_file_lines = None
	est_file_lines = None

	with open(act_file_name, 'r') as act_file:
		act_file_lines = [line.strip() for line in act_file.readlines()]

	with open(est_file_name, 'r') as est_file:
		est_file_lines = [line.strip() for line in est_file.readlines()]


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

def extractWlInfo(circuit_act_net_wl_map, circuit_est_net_wl_map, circuit_wl_err_map, circuit_net_info):
	total_wl = 0
	for sub_dir in circuit_act_net_wl_map:
		for net_id in circuit_act_net_wl_map[sub_dir]:
			total_wl += circuit_act_net_wl_map[sub_dir][net_id]


	union_fan_out = unionFanOut(circuit_net_info)

	fan_out_wl_cnt_map = {key: 0 for key in union_fan_out}
	fan_out_wl_ratio_map = {key: 0. for key in union_fan_out}
	fan_out_wl_share = {key: 0. for key in union_fan_out}

	circuits = list(circuit_act_net_wl_map.keys())

	for circuit in circuits:
		nets = list(circuit_act_net_wl_map[circuit].keys())
		for net in nets:
			wl_err = circuit_wl_err_map[circuit][net]
			if not isinstance(wl_err, (int,float)):
				circuit_act_net_wl_map[circuit].pop(net)
				circuit_est_net_wl_map[circuit].pop(net)
				circuit_wl_err_map[circuit].pop(net)

	for sub_dir in circuit_wl_err_map:
		num_nets = 0
		for net_num in circuit_wl_err_map[sub_dir]:
			assert sub_dir in circuit_net_info
			assert sub_dir in circuit_wl_err_map
			assert net_num in circuit_net_info[sub_dir]
			assert net_num in circuit_wl_err_map[sub_dir]

			net_fan_out = circuit_net_info[sub_dir][net_num]
			err_ratio = circuit_wl_err_map[sub_dir][net_num]
			net_wl = circuit_act_net_wl_map[sub_dir][net_num]
			assert err_ratio >= 0
			fan_out_wl_cnt_map[net_fan_out] += 1
			fan_out_wl_ratio_map[net_fan_out] += err_ratio
			fan_out_wl_share[net_fan_out] += net_wl


	for fan_out in union_fan_out:
		err_ratio = fan_out_wl_ratio_map[fan_out]
		wl_share = fan_out_wl_share[fan_out]
		cnt = fan_out_wl_cnt_map[fan_out]
		if not cnt == 0:
			fan_out_wl_ratio_map[fan_out] = err_ratio / cnt
			fan_out_wl_share[fan_out] = ((wl_share / total_wl) * 100)
		else:
			fan_out_wl_ratio_map.pop(fan_out)
			fan_out_wl_share.pop(fan_out)
			fan_out_wl_cnt_map.pop(fan_out)

	fan_out_vals = list(fan_out_wl_ratio_map.keys())
	wl_err = list(fan_out_wl_ratio_map.values())
	wl_share_vals = list(fan_out_wl_share.values())
	dist_vals = list(fan_out_wl_cnt_map.values())

	return fan_out_vals, wl_err, wl_share_vals, dist_vals


def extractTdInfo(circuit_act_net_td_map, circuit_est_net_td_map, circuit_td_err_map):

	assert len(circuit_act_net_td_map) == len(circuit_est_net_td_map)
	assert len(circuit_td_err_map) == len(circuit_act_net_td_map)

	circuits = list(circuit_act_net_td_map.keys())

	for circuit in circuits:
		nets = list(circuit_act_net_td_map[circuit].keys())
		for net in nets:
			keys = list(circuit_act_net_td_map[circuit][net].keys())
			for key in keys:
				if not key in circuit_td_err_map[circuit][net]:
					circuit_act_net_td_map[circuit][net].pop(key)
					circuit_est_net_td_map[circuit][net].pop(key)


	td_err_map = {}
	td_dist_vals_map = {}
	for circuit in circuits:
		nets = circuit_act_net_td_map[circuit].keys()
		for net in nets:
			curr_act_net_td = circuit_act_net_td_map[circuit][net]
			curr_est_net_td = circuit_est_net_td_map[circuit][net]
			curr_td_err = circuit_td_err_map[circuit][net]
			assert len(curr_act_net_td) == len(curr_est_net_td)
			assert len(curr_act_net_td) == len(curr_td_err)
			for key in curr_act_net_td:
				sink_num = key[0]
				dx = key[1]
				dy = key[2]
				td = curr_td_err[key]
				if (dx,dy) in td_err_map:
					assert (dx,dy) in td_dist_vals_map
					td_dist_vals_map[(dx,dy)] += 1
					td_err_map[(dx,dy)] += td
				else:
					td_dist_vals_map[(dx,dy)] = 1
					td_err_map[(dx,dy)] = td

	for key in td_err_map:
		td_err_map[key] /= td_dist_vals_map[key]

	dx_vals = [key[0] for key in td_err_map]
	dy_vals = [key[1] for key in td_err_map]
	td_dist_vals = [td_dist_vals_map[key] for key in td_err_map]

	return dx_vals, dy_vals, td_err_map, td_dist_vals_map

def plotWl(fan_out_vals, wl_err, wl_share_vals, wl_dist_vals):
	fig = plt.figure()
	val_sub_plot = fig.add_subplot(2, 2, 1)
	val_sub_plot.plot(fan_out_vals, wl_err, marker='o', color='b', label='Data')
	val_sub_plot.set_xscale("log")
	val_sub_plot.set_xlabel('Fan-out')
	val_sub_plot.set_ylabel('WL Error')
	# val_sub_plot.set_title('Line Plot of Dictionary Values')

	wl_share_sub_plot = fig.add_subplot(2, 2, 2)
	wl_share_sub_plot.plot(fan_out_vals, wl_share_vals, marker='o', color='b', label='Data')
	wl_share_sub_plot.set_xscale("log")
	wl_share_sub_plot.set_xlabel('Fan-out')
	wl_share_sub_plot.set_ylabel('Percentage of Wire Length Share in Total WL')
	wl_share_sub_plot.set_title('Distribution of Wire Length Percentage Based on Fan-Out')

	dist_sub_plot = fig.add_subplot(2, 2, 3)
	dist_sub_plot.plot(fan_out_vals, wl_dist_vals, marker='o', color='b', label='Data')
	dist_sub_plot.set_xscale("log")
	dist_sub_plot.set_xlabel('Fan-out')
	dist_sub_plot.set_ylabel('Number of Nets')
	dist_sub_plot.set_title('Number of Nets Based on Fan-Out')

def plotTd(dx_vals, dy_vals, td_err_map, td_dist_vals_map):
	min_dx = min(dx_vals)
	max_dx = max(dx_vals)
	min_dy = min(dy_vals)
	max_dy = max(dy_vals)
	x_bins = np.arange(min_dx, max_dx + 1, 1)
	y_bins = np.arange(min_dy, max_dy + 1, 1)

	td_err = []
	dist = []
	x_arr = []
	y_arr = []
	for x in x_bins:
		for y in y_bins:
			x_arr.append(x)
			y_arr.append(y)
			if (x,y) in td_err_map:
				td_err.append(td_err_map[(x,y)] * 100)
				dist.append(td_dist_vals_map[(x,y)])
			else:
				td_err.append(0.)
				dist.append(0)

	fig = plt.figure()

	td_err_sub_plot = fig.add_subplot(2, 1, 1)
	td_err_sub_plot.set_xlabel("dx")
	td_err_sub_plot.set_ylabel("dy")
	td_err_sub_plot.set_title("Difference Between Actual and Estimated Delay")
	_, _, _, im_td = td_err_sub_plot.hist2d(x_arr, y_arr, bins=[x_bins.size, y_bins.size], weights=td_err)

	dist_sub_plot = fig.add_subplot(2, 1, 2)
	dist_sub_plot.set_xlabel("dx")
	dist_sub_plot.set_ylabel("dy")
	dist_sub_plot.set_title("Number of Connections")
	_, _, _, im_dist = dist_sub_plot.hist2d(x_arr, y_arr, bins=[x_bins.size, y_bins.size], weights=dist, norm=matplotlib.colors.LogNorm())

	fig.colorbar(im_td, ax=td_err_sub_plot)
	fig.colorbar(im_dist, ax=dist_sub_plot)

def main(task_dir):
	sub_dirs = os.listdir(task_dir)

	circuit_act_net_wl_map = {}
	circuit_est_net_wl_map = {}
	circuit_wl_err_map = {}

	circuit_act_net_td_map = {}
	circuit_est_net_td_map = {}
	circuit_td_err_map = {}

	circuit_net_info = {}

	wl_fan_out_dict = {}
	print(f"Circuits: {sub_dirs}")

	for sub_dir in sub_dirs:
		print(f"Start processing {sub_dir}")
		circuit_dir = os.path.join(task_dir, sub_dir, "common")
		
		place_wl_act_dir = os.path.join(circuit_dir, "route_wl.txt")
		assert os.path.isfile(place_wl_act_dir)
		place_wl_est_dir = os.path.join(circuit_dir, "place_wl_est.txt")
		assert os.path.isfile(place_wl_est_dir)
		out_wl_ratio_file_name = os.path.join(circuit_dir, "wl_ratio.txt")

		print(f"\tGet WL info")
		circuit_act_net_wl_map[sub_dir], circuit_est_net_wl_map[sub_dir], circuit_wl_err_map[sub_dir] = \
			getCircuitInfo(place_wl_act_dir, place_wl_est_dir, out_wl_ratio_file_name)

		place_td_act_dir = os.path.join(circuit_dir, "route_td.txt")
		assert os.path.isfile(place_td_act_dir)
		place_td_est_dir = os.path.join(circuit_dir, "place_td_est.txt")
		assert os.path.isfile(place_td_est_dir)
		out_td_ratio_file_name = os.path.join(circuit_dir, "td_ratio.txt")

		print(f"\tGet td info")
		circuit_act_net_td_map[sub_dir], circuit_est_net_td_map[sub_dir], circuit_td_err_map[sub_dir] = \
			getCircuitInfo(place_td_act_dir, place_td_est_dir, out_td_ratio_file_name)

		circuit_fan_out_dir = os.path.join(circuit_dir, "net_info.txt")
		assert os.path.isfile(circuit_fan_out_dir)

		print(f"\tGet number of fan outs for each net")
		circuit_net_info[sub_dir] = getNetInfo(circuit_fan_out_dir)

	print("Get info for wl plot")
	fan_out_vals, wl_err, wl_share_vals, wl_dist_vals = \
		extractWlInfo(circuit_act_net_wl_map, circuit_est_net_wl_map, circuit_wl_err_map, circuit_net_info)

	print("Get info for td plot")
	dx_vals, dy_vals, td_err_map, td_dist_vals_map = \
		extractTdInfo(circuit_act_net_td_map, circuit_est_net_td_map, circuit_td_err_map)

	print("Plotting wl")
	plotWl(fan_out_vals, wl_err, wl_share_vals, wl_dist_vals)

	print("Plotting td")
	plotTd(dx_vals, dy_vals, td_err_map, td_dist_vals_map)



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