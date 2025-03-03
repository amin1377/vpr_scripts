import os
import argparse
import csv
import xml.etree.ElementTree as ET
import re

def extract_block_data(xml_file, circuit_name):
    """Extracts block names and their types from the VPR netlist XML file."""
    def clean_instance(instance):
        """Removes [number] from instance name"""
        return re.sub(r'\[\d+\]', '', instance)

    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # Find the block with name="[circuit_name].blif"
    target_name = f"{circuit_name}.blif"
    top_block = None

    for block in root.findall(".//block"):
        if block.get("name") == target_name:
            top_block = block
            break
    
    assert top_block is not None, f"No block found with name: {target_name}"


    # Iterate over its immediate child <block> elements
    block_map = {}
    type_map = {}
    for child in top_block.findall("block"):
        block_name = child.get("name")
        block_type = clean_instance(child.get("instance", ""))
        assert block_name not in block_map, f"Duplicate block name: {block_name}"
        block_map[block_name] = block_type
        if block_type not in type_map:
            type_map[block_type] = []
        type_map[block_type].append(block_name)
        
    return block_map, type_map

def count_blocks_by_layer(file_path):
    blocks_by_layer = {0:0, 1:0}
    found_block_name = False

    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()

            if not found_block_name:
                if line.startswith("#block name"):
                    found_block_name = True
                continue

            if line.startswith("#"):
                continue

            columns = line.split("\t")
            layer_num = int(columns[-2])
            
            assert layer_num in blocks_by_layer

            blocks_by_layer[layer_num] += 1

    return blocks_by_layer

def main(directory, out_file_name):
    data = []
    data.append(["Circuit", "Layer #0", "Layer #1"])
    for subdir in os.listdir(directory):
        subdir_path = os.path.join(directory, subdir, "common")
        if os.path.isdir(subdir_path):
            place_file_path = os.path.join(subdir_path, f"{subdir[:-2]}.pre-vpr.place")
            if os.path.isfile(place_file_path):
                blocks_by_layer = count_blocks_by_layer(place_file_path)
                row = []
                row.append(subdir)
                total_num_blocks = blocks_by_layer[0] + blocks_by_layer[1]
                for layer_num in [0, 1]:
                    row.append(f"{(blocks_by_layer[layer_num]/total_num_blocks)*100:.2f}")
                data.append(row)         
            else:
                print(f"Couldn't find {place_file_path}")
        else:
            print(f"Couldn't find {subdir_path}")

    with open(out_file_name, "w") as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerows(data)

def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_dir", required=True, help="File that contains the actual results")
    parser.add_argument("--out_file_name", required=True, help="Name of the output file")

    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = getArgs()
    main(args.task_dir, args.out_file_name)
