import os
import argparse
import csv

def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv_file", required=True, help="File(s) that contains the csv output of router lookahead")

    args = parser.parse_args()
    return args


def extractInfo(csv_file_name):
    data = {"CHANX": {}, "CHANY": {}}
    with open(csv_file_name, 'r', newline='', encoding='utf-8') as csv_file:
    # Create a CSV reader
    csv_reader = csv.reader(csv_file)

    # Skip the header row if it exists
    headers = next(csv_reader, None)

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

        if not seg_type in data["chan_type"]:
            data[chan_type][seg_type] = {}

        if not dx in data[chan_type][seg_type]:
            data[chan_type][seg_type][dx] = {}

        assert not dy in data[chan_type][seg_type][dx]
        data[chan_type][seg_type][dx][dy] = {"cong": cong_cost, "delay": delay_cost}

    return data

def getDxDyPlotData(data, chan_type, seg_type):
    delay_arr = []
    cong_arr = []

    plot_data = data[chan_type][seg_type]

    for x in plot_data:
        for y in plot_data[x]:
            delay_point = [x, y, plot_data[x][y]["delay"]]
            cong_point = [x, y, plot_data[x][y]["cong"]]

            delay_arr.append(delay_point)
            cong_arr.append(cong_point)

    return delay_arr, cong_arr

def makePlot(router_lookahead_data):
    for chan in router_lookahead_data:
        for seg in router_lookahead_data[chan]:
            delay_arr, cong_arr = getDxDyPlotData(router_lookahead_data, chan, seg)
            # Extract x, y, and data from the array
            x = [item[0] for item in delay_arr]
            y = [item[1] for item in delay_arr]
            data = [item[2] for item in delay_arr]

            # Create the heatmap using plt.hist2d
            plt.hist2d(x, y, bins=(np.unique(x), np.unique(y)), cmap='viridis', weights=data)

            # Add colorbar for reference
            plt.colorbar()

            # Set axis labels
            plt.xlabel('X')
            plt.ylabel('Y')

            # Add a title
            plt.title('Heatmap from 3D Data')

            # Show the plot
            plt.show()




def main(csv_file_name):
    data = extractInfo(csv_file_name)
    makePlot(data)

    

if __name__ == "__main__":
    args = getArgs()
    main(args.csv_file)