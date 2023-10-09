import os
import argparse

def checkHeader(header_line):
	bool header_is_correct = True
	header = line.split()
	header_is_correct &= (header[0] == "Net id")
	header_is_correct &=  ((header[-1] == "Expected wirelength") || (header[-1] == "Expected delay"))
	if len(header) > 2:
		header_is_correct &= (len(header) == 3)
		header_is_correct &= (header[1] == "Sink id")

	return header_is_correct


def getSortedDict(input_dict):
	sorted_dict = {k: input_dict[k] for k in sorted(input_dict)}
	return sorted_dict




def getNetValPair(file_lines):

	header = None
	net_val_pair = {}
	for line_num, line in enumerate(file_lines):
		if line_num == 0:
			header = line
			assert checkHeader(line)
		else:
			split_line = line.split()
			net_id = None
			sink_id = None
			val = None
			net_id = int(split_line[0])
			if len(split_line) == 2:
				val = flaot(split_line[1])
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






def main(act_file_name, est_file_name, out_file_name):
	act_file_lines = None
	est_file_lines = None

	with open(act_file_name, 'r') as act_file:
		act_file_lines = [line.strip() for line in act_file.readlines()]

	with open(est_file_name, 'r') as est_file:
		est_file_lines = [line.strip() for line in est_file.readlines()]

	header_line, act_file_net_val_pair = getNetValPair(act_file_lines)
	act_file_net_val_pair = getSortedDict(act_file_net_val_pair)

	_, est_file_net_val_pair = getNetValPair(est_file_lines)
	est_file_net_val_pair = getSortedDict(est_file_net_val_pair)

	with open(out_file_name, 'w') as out_file:
		assert len(act_file_net_val_pair) == len(est_file_net_val_pair)
		for net_id in act_file_net_val_pair:
			assert net_id in est_file_net_val_pair
			act_val = act_file_net_val_pair[net_id]
			est_val = est_file_net_val_pair[net_id]
			
			assert len(act_val) == len(est_val)
			assert isinstance(act_val, dict) == isinstance(est_val, dict) 

			if isinstance(act_val, dict):
				act_val = getSortedDict(act_val)
				est_val = getSortedDict(est_val)
			else:
				ratio = est_val / est_val
				out_file_name.write(f"")






def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--act_file_name", required=True, help="File that contains the actual results")
	parser.add_argument("--est_file_name", required=True, help="File that contains the actual results")
	parser.add_argument("--out_file_name", required=True, help="File that contains the actual results")

	args = parser.parse_args()
	return args

if __name__ == "__main__":
	args = getArgs()
	assert os.path.exists(args.act_file_name)
	assert os.path.exists(args.est_file_name)
	main(args.act_file_name, args.est_file_name, args.out_file_name)