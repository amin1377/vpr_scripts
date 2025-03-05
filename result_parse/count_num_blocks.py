import os
import argparse
import csv
import xml.etree.ElementTree as ET
import re

def extract_block_data(net_file, circuit_name):
    """Extracts block names and their types from the VPR netlist XML file."""
    def clean_instance(instance):
        """Removes [number] from instance name"""
        return re.sub(r'\[\d+\]', '', instance)

    tree = ET.parse(net_file)
    root = tree.getroot()
    
    assert root.attrib["name"] == f"{circuit_name}.net", f"Expected {circuit_name}.net, but got {root.attrib['name']}"
    

    # Iterate over its immediate child <block> elements
    block_map = {}
    type_map = {}
    for child in root.findall("block"):
        block_name = child.get("name")
        block_type = clean_instance(child.get("instance", ""))
        assert block_name not in block_map, f"Duplicate block name: {block_name}"
        block_map[block_name] = block_type
        if block_type not in type_map:
            type_map[block_type] = []
        type_map[block_type].append(block_name)
        
    return block_map, type_map

def count_blocks_by_layer(circuit_name, run_dir):
    net_file_path = os.path.join(run_dir, f"{circuit_name}.net")
    place_file_path = os.path.join(run_dir, f"{circuit_name}.place")
    blocks_type_layer = {}
    found_block_name = False

    block_map, type_map = extract_block_data(net_file_path, circuit_name)

    for type in type_map.keys():
        blocks_type_layer[type] = [0, 0]

    with open(place_file_path, 'r') as file:
        for line in file:
            line = line.strip()

            if not found_block_name:
                if line.startswith("#block name"):
                    found_block_name = True
                continue

            if line.startswith("#"):
                continue

            columns = line.split("\t")
            block_name = columns[0]
            layer_num = int(columns[-2])
            block_type = block_map[block_name]
            blocks_type_layer[block_type][layer_num] += 1

    return list(type_map.keys()), blocks_type_layer

def main(directory, out_file_name):
    circuit_block_type_layer = {}
    block_types = set()
    data = []
    data.append(["Circuit", "Layer #0", "Layer #1"])
    for subdir in os.listdir(directory):
        circuit_name = subdir[:-5]
        subdir_path = os.path.join(directory, subdir, "common")
        if os.path.isdir(subdir_path):
            print(f"Processing {circuit_name}")
            curr_block_types, blocks_type_layer = count_blocks_by_layer(circuit_name, subdir_path)
            block_types.update(curr_block_types)
            circuit_block_type_layer[circuit_name] = blocks_type_layer        
        else:
            print(f"Couldn't find {subdir_path}")
    
    print(block_types)
    print(circuit_block_type_layer)

    num_block_types = len(block_types)
    row = []
    table_data = []
    row.append("")
    row.append("Layer #0")
    for _ in range(num_block_types-1):
        row.append(f"")
    row.append("Layer #1")
    for _ in range(num_block_types-1):
        row.append(f"")
    table_data.append(row)

    row = []
    row.append("Circuit")
    for _ in [0, 1]:
        for block_type in block_types:
            row.append(block_type)
    table_data.append(row)

    for circuit_name, blocks_type_layer in circuit_block_type_layer.items():
        row = []
        row.append(circuit_name)
        circuit_num_blocks = circuit_block_type_layer[circuit_name]
        total_num_block_per_type = {}
        for block_type in block_types:
            if block_type not in circuit_num_blocks:
                total_num_block_per_type[block_type] = 0
            else:
                total_num_block_per_type[block_type] = circuit_num_blocks[block_type][0] + circuit_num_blocks[block_type][1]
        for layer_num in [0, 1]:
            for block_type in block_types:
                if block_type not in circuit_num_blocks:
                    row.append(0)
                else:
                    row.append(f"{circuit_num_blocks[block_type][layer_num]}/{total_num_block_per_type[block_type]:.2f}")
        table_data.append(row)

    with open(out_file_name, "w") as csv_file:
        csv_writer = csv.writer(csv_file, delimiter="\t")
        csv_writer.writerows(table_data)

def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_dir", required=True, help="File that contains the actual results")
    parser.add_argument("--out_file_name", required=True, help="Name of the output file")

    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = getArgs()
    main(args.task_dir, args.out_file_name)
