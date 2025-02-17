import xml.etree.ElementTree as ET
import random
import os
import argparse
from multiprocessing import Pool
import time
import io


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

def does_rr_graph_exist(output_dir, circuit, edge_removal_rate, mux_removal_rate):
    rr_graph_name = f"rr_graph_{circuit}_{int(edge_removal_rate*100)}_mux_{int(mux_removal_rate*100)}.xml"
    rr_graph_path = os.path.join(output_dir, rr_graph_name)
    return os.path.exists(rr_graph_path)

def adjust_fan_in_out(thread_arg):
    rr_graph_file_dir = thread_arg[0]
    circuit = thread_arg[1]
    edge_removal_rate = thread_arg[2]
    output_dir = thread_arg[3]

    mux_removal_rates = [0.05, 0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98]

    original_rr_graph_name = f"rr_graph_{circuit}_{int(edge_removal_rate*100)}.xml"

    print(f"Start working on {original_rr_graph_name}...")

    start_time = time.perf_counter()
    with io.open(rr_graph_file_dir, 'r') as f:
        tree = ET.parse(f)
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"\tParsing {original_rr_graph_name} is done ({execution_time:.2f} seconds)!")

    root = tree.getroot()
    rr_node_tag = root.find("rr_nodes")
    rr_edge_tag = root.find("rr_edges")

    nodes = {}
    max_x, max_y, max_layer = get_grid_loc(root)

    print(f"\tStart initializing auxiliary data structure for {original_rr_graph_name}..")
    start_time = time.perf_counter()
    for node_tag in rr_node_tag:
        node_id = int(node_tag.get("id"))
        loc_tag = node_tag.find("loc")
        loc_high = (int(loc_tag.get("xhigh")), int(loc_tag.get("yhigh")), int(loc_tag.get("layer")))
        nodes[node_id] = {"high_location": loc_high,
                          "out_edges": [],
                          "in_edges": []}

    grid_3d_edge_tag = []
    for l in range(max_layer+1):
      grid_3d_edge_tag.append([])
        for x in range(max_x+1):
            grid_3d_edge_tag[-1].append([])
            for y in range(max_y+1):
                grid_3d_edge_tag[-1][-1].append([])

    nods_under_consideration = set()

    original_edges = []
    for edge_tag in rr_edge_tag:
        src_node = int(edge_tag.get("src_node"))
        sink_node = int(edge_tag.get("sink_node"))
        original_edges.append(edge_tag)

        src_x = nodes[src_node]["high_location"][0]
        src_y = nodes[src_node]["high_location"][1]
        src_layer = nodes[src_node]["high_location"][2]

        sink_layer = nodes[sink_node]["high_location"][2]
        if src_layer != sink_layer:
            nods_under_consideration.add(src_node)
            nods_under_consideration.add(sink_node)
            grid_3d_edge_tag[src_layer][src_x][src_y].append(edge_tag)

    for edge_tag in rr_edge_tag:
        src_node = int(edge_tag.get("src_node"))
        sink_node = int(edge_tag.get("sink_node"))
        if src_node in nods_under_consideration or sink_node in nods_under_consideration:
            nodes[src_node]["out_edges"].append(edge_tag)
            nodes[sink_node]["in_edges"].append(edge_tag)

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"\tDone initializing auxiliary data structure for {original_rr_graph_name} ({execution_time:.2f} seconds)!")



    print(f"Original number of edges for {original_rr_graph_name}: {len(original_edges)}")
    for mux_removal_rate in mux_removal_rates:
        # if does_rr_graph_exist(output_dir, circuit, edge_removal_rate, mux_removal_rate):
        #     continue
        rr_graph_name = f"rr_graph_{circuit}_{int(edge_removal_rate*100)}_mux_{int(mux_removal_rate*100)}.xml"
        edges_to_remove = []
        for l in range(max_layer+1):
            for x in range(max_x+1):
                for y in range(max_y+1):
                    for edge_tag in grid_3d_edge_tag[l][x][y]:
                        src_node = int(edge_tag.get("src_node"))
                        sink_node = int(edge_tag.get("sink_node"))

                        fan_in_edges = nodes[src_node]["in_edges"]
                        fan_out_edges = nodes[sink_node]["out_edges"]
                        num_elem = int(len(fan_in_edges) * mux_removal_rate)
                        edges_to_remove.extend(random.sample(fan_in_edges, num_elem))
                        num_elem = int(len(fan_out_edges) * mux_removal_rate)
                        edges_to_remove.extend(random.sample(fan_out_edges, num_elem))

        print(f"\tStart removing {len(edges_to_remove)} number of edges from {rr_graph_name}...")
        start_time = time.perf_counter()
        set_edges_to_remove = set(edges_to_remove)
        remaining_edgs = [edge for edge in original_edges if edge not in set_edges_to_remove]
        rr_edge_tag[:] = remaining_edgs
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        print(f"\tDone removing {len(edges_to_remove)} number of edges from {rr_graph_name} ({execution_time:.2f} seconds) - {len(rr_edge_tag)} edges remaining!")
        print(f"\tStart writing {rr_graph_name}")
        start_time = time.perf_counter()
        # use IO buffer to write
        with io.open(os.path.join(output_dir, rr_graph_name), 'w') as f:
            tree.write(f, encoding='utf-8', xml_declaration=False)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        print(f"\tDone writing {rr_graph_name} ({execution_time:.2f} seconds)!")

        print(f"Writing {rr_graph_name} is complete!")



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
    non_existing_rr_graphs = []

    number_of_threads = int(args.j)

    edge_removal_rates = [0.50, 0.65, 0.80]

    thread_args = []
    for circuit in ["EKF-SLAM_Jacobians_stratixiv_arch_timing"]:
        for edge_removal_rate in [0.8]:
            print(f"{circuit} - Edge removal rate: {edge_removal_rate}...")
            rr_graph_name = f"rr_graph_{circuit}_{int(edge_removal_rate*100)}.xml"
            rr_graph_dir = os.path.join("/home/mohagh18/tmp/resources", f"{rr_graph_name}")
            if not os.path.isfile(rr_graph_dir):
                non_existing_rr_graphs.append([circuit, edge_removal_rate])
            elif circuit == "directrf_stratixiv_arch_timing" or circuit == "bitcoin_miner_stratixiv_arch_timing" or circuit == "LU_Network_stratixiv_arch_timing" or \
                    circuit == "mes_noc_stratixiv_arch_timing" or circuit == "gsm_switch_stratixiv_arch_timing" or circuit == "sparcT1_chip2_stratixiv_arch_timing":
                continue
            else:
                thread_args.append([rr_graph_dir, circuit, edge_removal_rate, args.output_dir])

    print(f"Non-existing RR Graphs: {non_existing_rr_graphs}")

    pool = Pool(number_of_threads)
    pool.map(adjust_fan_in_out, thread_args)
    pool.close()

    print(f"Done with writing all RR Graphs!")



if __name__ == "__main__":
    main()
