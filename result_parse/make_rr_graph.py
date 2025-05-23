import xml.etree.ElementTree as ET
import random
import os
import argparse
from multiprocessing import Pool
import time


def get_grid_loc(root_tag):
    grid_tag = root_tag.find("grid")
    max_x = 0
    max_y = 0
    max_layer = 0
    for grid_loc_tag in grid_tag:
        loc_x = int(grid_loc_tag.get("x"))
        loc_y = int(grid_loc_tag.get("y"))
        loc_layer = int(grid_loc_tag.get("layer"))
        if loc_x > max_x:
            max_x = loc_x
        if loc_y > max_y:
            max_y = loc_y
        if loc_layer > max_layer:
            max_layer = loc_layer
    return max_x, max_y, max_layer

def remove_inter_die_edge(thread_arg):
    rr_graph_file_dir = thread_arg[0]
    edge_removal_rate = thread_arg[1]
    circuit = thread_arg[2]
    output_dir = thread_arg[3]

    rr_graph_name = f"rr_graph_{circuit}_{int(edge_removal_rate*100)}.xml"

    print(f"Start working on {rr_graph_name}...")

    start_time = time.perf_counter()
    tree = ET.parse(rr_graph_file_dir)
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"\tParsing {rr_graph_name} is done ({execution_time:.6f} seconds)!")
    root = tree.getroot()
    rr_node_tag = root.find("rr_nodes")
    rr_edge_tag = root.find("rr_edges")

    nodes = {}

    max_x, max_y, max_layer = get_grid_loc(root)
    print(f"\t{circuit} FPGA size: {max_x} {max_y} {max_layer}")

    for node_tag in rr_node_tag:
        node_id = int(node_tag.get("id"))
        loc_tag = node_tag.find("loc")
        loc_high = (int(loc_tag.get("xhigh")), int(loc_tag.get("yhigh")), int(loc_tag.get("layer")))
        loc_low = (int(loc_tag.get("xlow")), int(loc_tag.get("ylow")), int(loc_tag.get("layer")))
        type = node_tag.get("type")
        nodes[node_id] = {"high_location": loc_high, "low_location": loc_low, "type": type, "length": None}
        if type == "CHANX" or type == "CHANY":
            seg_tag = node_tag.find("segment")
            seg_id = int(seg_tag.get("segment_id"))
            if seg_id == 0:
                nodes[node_id]["length"] = 4
            else:
                assert seg_id == 1
                nodes[node_id]["length"] = 16

    grid_3d_edge_tag = []

    for x in range(max_x+1):
        grid_3d_edge_tag.append([])
        for y in range(max_y+1):
            grid_3d_edge_tag[-1].append([])
            for l in range(max_layer+1):
                # grid[-1].append({"total": 0, "L4->L4": 0, "L4->L16": 0, "L16->L16": 0})
                grid_3d_edge_tag[-1][-1].append([])

    for edge_tag in rr_edge_tag:
        src_node = int(edge_tag.get("src_node"))
        sink_node = int(edge_tag.get("sink_node"))
        src_x = nodes[src_node]["high_location"][0]
        src_y = nodes[src_node]["high_location"][1]
        src_layer = nodes[src_node]["high_location"][2]

        sink_layer = nodes[sink_node]["high_location"][2]
        if src_layer != sink_layer:
            grid_3d_edge_tag[src_x][src_y][src_layer].append(edge_tag)

    edges_to_remove = []
    for x in range(max_x+1):
        for y in range(max_y+1):
            for l in range(max_layer+1):
                num_elem = int(len(grid_3d_edge_tag[x][y][l]) * edge_removal_rate)
                edges_to_remove.extend(random.sample(grid_3d_edge_tag[x][y][l], num_elem))

    print(f"\tStart removing {len(edges_to_remove)} number of edges from {rr_graph_name}!")
    start_time = time.perf_counter()
    set_edges_to_remove = set(edges_to_remove)
    remaining_edgs = [edge for edge in list(rr_edge_tag) if edge not in set_edges_to_remove]
    rr_edge_tag[:] = remaining_edgs
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"\tDone removing {len(edges_to_remove)} number of edges from {rr_graph_name} ({execution_time:.6f} seconds)!")

    print(f"\tStart writing {rr_graph_name}")
    start_time = time.perf_counter()
    tree.write(os.path.join(output_dir, rr_graph_name), encoding='utf-8', xml_declaration=False)
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"\tDone writing {rr_graph_name} ({execution_time:.6f} seconds)!")

    print(f"Writing {rr_graph_name} is complete!")
    
def get_remaining_rr_graph(output_dir, circuits, removal_rates):
    remaning_circuits_removal_rate = []
    for circuit in circuits:
        for removal_rate in removal_rates:
            rr_graph_name = f"rr_graph_{circuit}_{int(removal_rate*100)}.xml"
            rr_graph_path = os.path.join(output_dir, rr_graph_name)
            if not os.path.exists(rr_graph_path):
                remaning_circuits_removal_rate.append([circuit, removal_rate])
            else:
                print(f"{rr_graph_name} already exists!")
    return remaning_circuits_removal_rate

def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtr_run_dir", required=True, help="VTR task run directory")
    parser.add_argument("--output_dir", required=True, help="Output direcotry to dump new RR Graph files")
    parser.add_argument("-j", required=True, help="Number of available threads")


    args = parser.parse_args()
    return args

def main():
    args = getArgs()
    rr_graph_resource_dir = os.path.abspath(args.vtr_run_dir)
    circuit_dirs = os.listdir(rr_graph_resource_dir)
    circuits = [circuit.split(".")[0] for circuit in circuit_dirs]

    number_of_threads = int(args.j)
    removal_rates = [0.05, 0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98]
    remaining_circuits_removal_rate = get_remaining_rr_graph(args.output_dir, circuits, removal_rates)
    print(f"Remaining circuits and removal rates: {remaining_circuits_removal_rate}")

    thread_args = []
    for circuit, removal_rate in remaining_circuits_removal_rate:
        print(f"{circuit} {removal_rate}")
        rr_graph_dir = os.path.join(rr_graph_resource_dir, f"{circuit}.blif", "common", "rr_graph.xml")
        assert os.path.isfile(rr_graph_dir), rr_graph_dir
        thread_args.append([rr_graph_dir, removal_rate, circuit, args.output_dir])


    pool = Pool(number_of_threads)
    pool.map(remove_inter_die_edge, thread_args)
    pool.close()

    print(f"Done with writing all RR Graphs!")



if __name__ == "__main__":
    main()
