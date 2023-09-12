import os
import re

def check_vpr_output(dir1):
    matching_subdirs = os.listdir(dir1)
    print(f"Common Circuits: {matching_subdirs}\n\n")

    for subdir in matching_subdirs:
        subdir_path1 = os.path.join(dir1, subdir, "common")
        vpr_out_file1 = os.path.join(subdir_path1, "vpr.out")

        if os.path.isfile(vpr_out_file1):
            with open(vpr_out_file1, "r") as file1:
                contents1 = file1.read()

                circuit_name = subdir_path1.split("/")[-2]

                if not "VPR succeeded" in contents1:
                    print(f"{circuit_name} failed!")
                    continue

                find_and_print_lines(circuit_name, vpr_out_file1, contents1)
                

def find_and_print_lines(circuit_name, vpr_out_file1, contents1):
    lines1 = contents1.split("\n")
    
    cpd = -1
    wl = -1

    for line in lines1:
        if "Final critical path delay" in line:
            pattern = r'Final critical path delay \(least slack\)\s*:\s*(.*) ns'
            match = re.search(pattern, line)
            assert match
            if match:
                number = float(match.group(1))
                cpd = number
        elif "Total wirelength:" in line:
            pattern = r'\s*Total wirelength\s*:\s*(.*), average .*'
            match = re.search(pattern, line)
            assert match
            if match:
                number = float(match.group(1))
                wl = number

    assert cpd > 0
    assert wl > 0

    print(f"{circuit_name}\t{cpd}\t{wl}")

if __name__ == "__main__":
    directory1 = "/home/amin/wintermute_mount/run_koios/run003/aman_3d_limited.xml"
    check_vpr_output(directory1)
