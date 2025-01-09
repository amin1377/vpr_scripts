import xml.etree.ElementTree as ET
import random

tree = ET.parse("/home/mohagh18/tmp/tmp_run/rr_graph.xml")
root = tree.getroot()
rr_node_tag = root.find("rr_nodes")
rr_edge_tag = root.find("rr_edges")

nodes = {}
edges = {}

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
for l in range(max_layer+1):
    grid.append([])
    grid_3d_edge_tag.append([])
    for x in range(max_x+1):
        grid[-1].append([])
        grid_3d_edge_tag[-1].append([])
        for y in range(max_y+1):
            # grid[-1].append({"total": 0, "L4->L4": 0, "L4->L16": 0, "L16->L16": 0})
            grid[-1][-1].append(0)
            grid_3d_edge_tag[-1][-1].append([])

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
        print(f"Fan-in: {fan_in} (L4: {num_l4_source}, L16: {num_l16_source}) Fan-out: {fan_out} (L4: {num_l4_sink}, L16: {num_l16_sink})")

to_be_removed_edge_tag = []
for l in range(max_layer+1):
    for x in range(max_x+1):
        for y in range(max_y+1):
            num_elem = int(len(grid_3d_edge_tag[l][x][y]) * 0.98)
            print(f"Location ({x},{y},{l}) remove {num_elem} connections out of {len(grid_3d_edge_tag[l][x][y])}!")
            to_be_removed_edge_tag.extend(random.sample(grid_3d_edge_tag[l][x][y], num_elem))

for edge_tag in to_be_removed_edge_tag:
    # src_node = int(edge_tag.get("src_node"))
    # sink_node = int(edge_tag.get("sink_node"))
    # print(f"source node id: {src_node} - sink node id: {sink_node}")
    rr_edge_tag.remove(edge_tag)

tree.write('updated.xml', encoding='utf-8', xml_declaration=True)


print(grid[0])
print(grid[1])

acc = [0, 0] 
num = [0, 0]
for x in range(max_x+1):
    for y in range(max_y+1):
        if x != 0 and y != 0:
            acc[0] += grid[0][x][y]
            num[0] += 1
            acc[1] += grid[1][x][y]
            num[1] += 1
        if grid[0][x][y] == 0:
            continue
        if abs(grid[0][x][y] - grid[1][x][y])/grid[0][x][y]  > 0.5:
            print(f"x: {x} y: {y} layer_0: {grid[0][x][y]} layer_1: {grid[1][x][y]}")
print(f"Layer 0 avg: {acc[0]/num[0]} - Layer 1 avg: {acc[1]/num[1]}")

