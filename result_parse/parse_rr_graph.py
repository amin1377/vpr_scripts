import xml.etree.ElementTree as ET
import random
import argparse


def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rr_graph", required=True, help="Path to RR Graph file")

    args = parser.parse_args()
    return args

def main():
    args = getArgs()
    rr_graph_file_path = args.rr_graph
    print(f"Start parsing {rr_graph_file_path}...")
    tree = ET.parse(rr_graph_file_path)
    print(f"Parsing is done!")
    root = tree.getroot()
    rr_node_tag = root.find("rr_nodes")
    rr_edge_tag = root.find("rr_edges")

    nodes = {}
    max_x = 0
    max_y = 0
    max_layer = 0

    for node_tag in rr_node_tag:
        node_id = int(node_tag.get("id"))
        loc_tag = node_tag.find("loc")
        loc_high = (int(loc_tag.get("xhigh")), int(loc_tag.get("yhigh")), int(loc_tag.get("layer")))
        loc_low = (int(loc_tag.get("xlow")), int(loc_tag.get("ylow")), int(loc_tag.get("layer")))
        type = node_tag.get("type")
        nodes[node_id] = {"high_location": loc_high, "low_location": loc_low, "type": type, "sink_nodes": [], "source_nodes": [], "length": None}
        if type == "CHANX" or type == "CHANY":
            seg_tag = node_tag.find("segment")
            seg_id = int(seg_tag.get("segment_id"))
            if seg_id == 0:
                nodes[node_id]["length"] = 4
            else:
                assert seg_id == 1
                nodes[node_id]["length"] = 16
        if loc_high[0] > max_x:
            max_x = loc_high[0]
        if loc_low[0] > max_x:
            max_x = loc_low[0]

        if loc_high[1] > max_y:
            max_y = loc_high[1]
        if loc_low[1] > max_y:
            max_y = loc_low[1]
        
        if loc_high[2] > max_layer:
            max_layer = loc_high[2]

    for edge_tag in rr_edge_tag:
        sink_node = int(edge_tag.get("sink_node"))
        src_node = int(edge_tag.get("src_node"))
        switch_id = int(edge_tag.get("switch_id"))
        nodes[src_node]["sink_nodes"].append(sink_node)
        nodes[sink_node]["source_nodes"].append(src_node)

    grid = []
    grid_3d_edge_tag = []
    mux_fan_in = []
    mux_fan_out = []
    for l in range(max_layer+1):
        grid.append([])
        grid_3d_edge_tag.append([])
        mux_fan_in.append([])
        mux_fan_out.append([])
        for x in range(max_x+1):
            grid[-1].append([])
            grid_3d_edge_tag[-1].append([])
            mux_fan_in[-1].append([])
            mux_fan_out[-1].append([])
            for y in range(max_y+1):
                # grid[-1].append({"total": 0, "L4->L4": 0, "L4->L16": 0, "L16->L16": 0})
                grid[-1][-1].append(0)
                grid_3d_edge_tag[-1][-1].append([])
                mux_fan_in[-1][-1].append({"total": 0, "l4": 0, "l16": 0})
                mux_fan_out[-1][-1].append({"total": 0, "l4": 0, "l16": 0})

    for edge_tag in rr_edge_tag:
        src_node = int(edge_tag.get("src_node"))
        sink_node = int(edge_tag.get("sink_node"))
        switch_id = int(edge_tag.get("switch_id"))
        src_x = nodes[src_node]["high_location"][0]
        src_y = nodes[src_node]["high_location"][1]
        src_layer = nodes[src_node]["high_location"][2]

        sink_layer = nodes[sink_node]["high_location"][2]
        if src_layer != sink_layer:
            grid_3d_edge_tag[src_layer][src_x][src_y].append(edge_tag)
            grid[src_layer][src_x][src_y] += 1
            num_l4_source = 0
            num_l16_source = 0
            for parent_source in nodes[src_node]["source_nodes"]:
                node_type = nodes[parent_source]["type"]
                assert node_type == "CHANX" or node_type == "CHANY"
                chan_len = nodes[parent_source]["length"]
                if chan_len == 4:
                    num_l4_source += 1
                else:
                    assert chan_len == 16
                    num_l16_source += 1
                
            num_l4_sink = 0
            num_l16_sink = 0
            for parent_sink in nodes[sink_node]["sink_nodes"]:
                node_type = nodes[parent_sink]["type"]
                assert node_type == "CHANX" or node_type == "CHANY"
                chan_len = nodes[parent_source]["length"]
                if chan_len == 4:
                    num_l4_sink += 1
                else:
                    assert chan_len == 16
                    num_l16_sink += 1
            
                
            fan_in = len(nodes[src_node]["source_nodes"])
            fan_out = len(nodes[sink_node]["sink_nodes"])

            mux_fan_in[src_layer][src_x][src_y]["total"] += fan_in
            mux_fan_in[src_layer][src_x][src_y]["l4"] += num_l4_source
            mux_fan_in[src_layer][src_x][src_y]["l16"] += num_l16_source
            
            mux_fan_out[src_layer][src_x][src_y]["total"] += fan_out
            mux_fan_out[src_layer][src_x][src_y]["l4"] += num_l4_sink
            mux_fan_out[src_layer][src_x][src_y]["l16"] += num_l16_sink

            print(f"({src_node}->{sink_node}): Fan-in: {fan_in} (L4: {num_l4_source}, L16: {num_l16_source}) Fan-out: {fan_out} (L4: {num_l4_sink}, L16: {num_l16_sink})")

    total_fan_in = [0, 0]
    total_fan_out = [0, 0]
    
    for x in range(max_x+1):
        for y in range(max_y+1):
            if x != 0 and y != 0:
                for l in range(max_layer+1):
                    total_fan_in[l] += mux_fan_in[l][x][y]["total"]
                    total_fan_out[l] += mux_fan_out[l][x][y]["total"]

                    mux_fan_in[l][x][y]["total"] /= grid[l][x][y]
                    mux_fan_in[l][x][y]["l4"] /= grid[l][x][y]
                    mux_fan_in[l][x][y]["l16"] /= grid[l][x][y]

                    mux_fan_out[l][x][y]["total"] /= grid[l][x][y]
                    mux_fan_out[l][x][y]["l4"] /= grid[l][x][y]
                    mux_fan_out[l][x][y]["l16"] /= grid[l][x][y]



    acc = [0, 0] 
    num = [0, 0]
    for x in range(max_x+1):
        for y in range(max_y+1):
            if x != 0 and y != 0:
                for l in range(max_layer+1):
                    acc[l] += grid[l][x][y]
                    num[l] += 1
                    print(f"{x} {y} {l}")
                    print(f"\t Number of inter-die connections: {grid[l][x][y]}")
                    print(f'\t Average inter-die edge fan-in: {mux_fan_in[l][x][y]["total"]:.2f} (l4: {mux_fan_in[l][x][y]["l4"]:.2f} l16: {mux_fan_in[l][x][y]["l16"]:.2f})')
                    print(f'\t Average inter-die edge fan-out: {mux_fan_out[l][x][y]["total"]:.2f} (l4: {mux_fan_out[l][x][y]["l4"]:.2f} l16: {mux_fan_out[l][x][y]["l16"]:.2f})')


    print(f"Average number of inter-die connections per tile: 0>1: {acc[0]/num[0]:.2f} - 1->0: {acc[1]/num[1]:.2f}")
    print(f"Average fan-in and fan-out per inter-die connection: 0: Fan-in {total_fan_in[0]/acc[0]:.2f}, Fan-out {total_fan_out[0]/acc[0]:.2f} - 1: Fan-in {total_fan_in[1]/acc[1]:.2f}, Fan-out {total_fan_out[1]/acc[1]:.2f}")



if __name__ == "__main__":
    main()

