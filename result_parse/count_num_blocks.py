import os

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

def main(directory):
    for subdir in os.listdir(directory):
        subdir_path = os.path.join(directory, subdir, "common")
        if os.path.isdir(subdir_path):
            place_file_path = os.path.join(subdir_path, f"{subdir[:-2]}.pre-vpr.place")
            if os.path.isfile(place_file_path):
                blocks_by_layer = count_blocks_by_layer(place_file_path)

                print(f"{subdir}: ", end="\t")
                total_num_blocks = blocks_by_layer[0] + blocks_by_layer[1]
                for layer_num in [0, 1]:
                    print(f"{blocks_by_layer[layer_num]}({(blocks_by_layer[layer_num]/total_num_blocks)*100:.2f}%)", end="\t")
                print()
                
            else:
                print(f"Couldn't find {place_file_path}")

# Replace '/path/to/dir' with the actual path to the directory you want to process
main('/home/amin/wintermute_mount/run_koios/run001/aman_3d_coffe.xml')
