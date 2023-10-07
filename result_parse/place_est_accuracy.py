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




def getNetValPair(file_lines):

	header = None
	net_val_pair = {}
	for line_num, line in enumerate(file_lines):
		if line_num == 0:
			assert checkHeader(line)
		else:
			split_line = 
			net_id = int()




def main(act_file_name, est_file_name):
	act_file_lines = None
	est_file_lines = None

	with open(act_file_name, 'r') as act_file:
		act_file_lines = [line.strip() for line in act_file.readlines()]

	with open(est_file_name, 'r') as est_file:
		est_file_lines = [line.strip() for line in est_file.readlines()]

	act_file_net_val_pair = getNetValPair(act_file_lines)
	est_file_net_val_pair = getNetValPair(est_file_lines)




def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--act_file_name", required=True, help="File that contains the actual results")
	parser.add_argument("--est_file_name", required=True, help="File that contains the actual results")

	args = parser.parse_args()
	return args

if __name__ == "__main__":
	args = getArgs()
	assert os.path.exists(args.act_file_name)
	assert os.path.exists(args.est_file_name)
	main(args.act_file_name, args.est_file_name)