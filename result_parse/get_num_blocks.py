import os
import re

def get_block_count(vpr_out_file):
    with open(vpr_out_file, 'r') as file:
        content = file.read()

    pattern = r'Netlist\n\s+(\d+)\s+blocks of type: (\w+)'
    matches = re.findall(pattern, content)
    block_counts = {}
    for count, block_type in matches:
        assert block_type == "io" or block_type == "dsp_top" or block_type == "clb" or block_type == "memory" or block_type == "tsv_hole"
        block_counts[block_type] = int(count)

    return block_counts


def main(directory):
    subdirs = [subdir for subdir in os.listdir(directory) if os.path.isdir(os.path.join(directory, subdir))]

    for subdir in subdirs:
        vpr_out_file = os.path.join(directory, subdir, "common", "vpr.out")
        
        if os.path.exists(vpr_out_file):
            block_counts = get_block_count(vpr_out_file)
            print(f"{subdir}", end="\t")
            for block_type in ["io", "clb", "memory", "dsp_top", "tsv_hole"]:
                print(f"{block_counts[block_type]}", end="\t")
        else:
            print(f"{vpr_out_file} doesn't exist")
        print()

if __name__ == "__main__":
    directory = "/home/amin/wintermute_mount/run_koios_min_size/run_3d"
    main(directory)
