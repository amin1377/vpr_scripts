import os
import argparse
import csv
import matplotlib.pyplot as plt
import numpy as np

def getArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("--csv_file", nargs='*', required=True, help="File(s) that contains the csv output of router lookahead")

	args = parser.parse_args()
	return args


def extractInfo(csv_file_name):
	data = {"CHANX": {}, "CHANY": {}}
	with open(csv_file_name, 'r', newline='', encoding='utf-8') as csv_file:
		# Create a CSV reader
		csv_reader = csv.DictReader(csv_file)

		# Process each row in the CSV file
		for row in csv_reader:
			from_layer = int(row["from_layer"])
			chan_type = row["chan_type"] 
			seg_type = int(row["seg_type"]) 
			to_layer = int(row["to_layer"]) 
			delta_x = int(row["delta_x"]) 
			delta_y = int(row["delta_y"]) 
			cong_cost = float(row["cong_cost"]) 
			delay_cost = float(row["delay_cost"])
			assert from_layer == to_layer
			assert chan_type in data

			if not seg_type in data[chan_type]:
				data[chan_type][seg_type] = {}

			if not delta_x in data[chan_type][seg_type]:
				data[chan_type][seg_type][delta_x] = {}

			assert not delta_y in data[chan_type][seg_type][delta_x]
			data[chan_type][seg_type][delta_x][delta_y] = {"cong": cong_cost, "delay": delay_cost}

	return data

def getDxDyPlotData(data, chan_type, seg_type, cost_type):
	cost_arr = []

	plot_data = data[chan_type][seg_type]

	for x in plot_data:
		for y in plot_data[x]:
			cost_point = [x, y, plot_data[x][y][cost_type]]

			cost_arr.append(cost_point)

	return cost_arr

def makePlot(router_lookahead_data, fig, ax, chan_type, seg_type, cost_type):
	cost_arr = getDxDyPlotData(router_lookahead_data, chan_type, seg_type, cost_type)
	# Extract x, y, and data from the array
	x = np.array([item[0] for item in cost_arr])
	y = np.array([item[1] for item in cost_arr])
	data = np.array([item[2] for item in cost_arr])

	# Create the heatmap using plt.hist2d
	h = ax.hist2d(x, y, bins=(np.unique(x), np.unique(y)), cmap='viridis', weights=data)

	# Add colorbar for reference
	fig.colorbar(h[3], ax=ax)

	ax.set_title(f"CHAN: {chan_type}, Seg: {seg_type}, Cost: {cost_type}")

def getRouterLookaheadDataDiff(router_looaheads_data):
	assert len(router_looaheads_data) == 2

	diff_data = {"CHANX": {}, "CHANY": {}}

	for chan in router_looaheads_data[0]:
		for seg in router_looaheads_data[0][chan]:
			if not seg in diff_data[chan]:
				diff_data[chan][seg] = {}
			for dx in router_looaheads_data[0][chan][seg]:
				if not dx in diff_data[chan][seg]:
					diff_data[chan][seg][dx] = {}
				for dy in router_looaheads_data[0][chan][seg][dx]:
					if not dy in diff_data[chan][seg][dx]:
						diff_data[chan][seg][dx][dy] = {}
					
					diff_data[chan][seg][dx][dy]["cong"] = 0.
					diff_data[chan][seg][dx][dy]["delay"] = 0.

					for cost_type in {"cong", "delay"}:
						first_cost = router_looaheads_data[0][chan][seg][dx][dy][cost_type]
						second_cost = router_looaheads_data[1][chan][seg][dx][dy][cost_type]
						try:
							diff_data[chan][seg][dx][dy][cost_type] = abs(((second_cost - first_cost) / (first_cost))) * 100
						except:
							diff_data[chan][seg][dx][dy][cost_type] = 0
							print(f"First cost was zero[{chan}][{seg}][{dx}][{dy}][{cost_type}]: {first_cost}, {second_cost}")

	return diff_data



def main(csv_file_names):
	print(csv_file_names)
	assert len(csv_file_names) == 1 or len(csv_file_names) == 2
	router_looaheads_data = []
	num_x = 4
	num_y = 2

	for csv_file_name in csv_file_names:
		data = extractInfo(csv_file_name)
		fig, axs = plt.subplots(num_y, num_x)

		for y in range(num_y):
			for x in range(num_x):
				chan_type  = "CHANX" if y == 0 else "CHANY"
				seg_type = 0 if x % 2 == 0 else 1
				cost_type = "delay" if int(x / 2) == 0 else "cong"
				print(f"Chan type: {chan_type}, Seg type: {seg_type}, cost_type: {cost_type}")
				makePlot(data, fig, axs[y, x], chan_type, seg_type, cost_type)
			
		router_looaheads_data.append(data)

	if len(router_looaheads_data) == 2:
		fig, axs = plt.subplots(num_y, num_x)
		diff_data = getRouterLookaheadDataDiff(router_looaheads_data)
		for y in range(num_y):
			for x in range(num_x):
				chan_type  = "CHANX" if y == 0 else "CHANY"
				seg_type = 0 if x % 2 == 0 else 1
				cost_type = "delay" if int(x / 2) == 0 else "cong"
				makePlot(diff_data, fig, axs[y, x], chan_type, seg_type, cost_type)



	plt.tight_layout()
	plt.show()

	

if __name__ == "__main__":
	args = getArgs()
	main(args.csv_file)