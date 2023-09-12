import os
import re

def get_total_inter_die_conn(vpr_out_file):
    with open(vpr_out_file, 'r') as file:
        content = file.read()

    pattern = r'Netlist\n\s+(\d+)\s+blocks of type: (\w+)'
    matches = re.findall(pattern, content)
    block_counts = {}
    for count, block_type in matches:
        block_counts[block_type] = int(count)

    total_num_conn = 0
    for block_type in block_counts:
        count = block_counts[block_type]
        if block_type == "io":
            total_num_conn += (count * 4)
        elif block_type == "clb":
            total_num_conn += (count * 20)
        elif block_type == "dsp_top":
            total_num_conn += (count * 74)
        elif block_type == "memory":
            total_num_conn += (count * 40)
        else:
            assert block_type == "tsv_hole"

    return total_num_conn




def get_layer_counts(route_file):
    layer_count = 0
    previous_layer = -1

    with open(route_file, 'r') as file:
        for line in file:
            if line.startswith("Net"):
                previous_layer = -1
                continue  # Skip until the "Net" section
            elif line.startswith("Node"):
                elements = line.split()
                assert len(elements) > 5
                node_type = elements[2]
                coordinate = elements[3].strip('()').split(',')
                current_layer = int(coordinate[0])
                if node_type == "SINK":
                    previous_layer = -1
                elif previous_layer == -1:
                    previous_layer = current_layer
                elif current_layer != previous_layer:
                    layer_count += 1
                    previous_layer = current_layer


    return layer_count

def main(directory):
    subdirs = [subdir for subdir in os.listdir(directory) if os.path.isdir(os.path.join(directory, subdir))]

    for subdir in subdirs:
        total_con = get_total_inter_die_conn(os.path.join(directory, subdir, "common", "vpr.out"))
        route_file = os.path.join(directory, subdir, "common", subdir[:-2] + ".pre-vpr" + ".route")
        if os.path.exists(route_file):
            layer_count = get_layer_counts(route_file)
            print(f"{subdir}\t{layer_count}({(layer_count/total_con)*100:.2f}%)")
        else:
            print(f"{route_file} doesn't exist")

if __name__ == "__main__":
    directory = "/home/amin/wintermute_mount/run_koios/run001/aman_3d_coffe.xml"
    main(directory)
