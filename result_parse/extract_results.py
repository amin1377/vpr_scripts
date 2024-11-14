import os
import re   
import argparse
import csv

def extract_circuit_info(contents):
    lines = contents.split("\n")
    
    cpd = -1
    wl = -1
    pack_time = -1
    place_time = -1
    route_time = -1
    total_time = -1

    for line in lines:
        pack_time_line = re.search(r"# Packing took ([\d.]+) seconds", line)
        place_time_line = re.search(r"# Placement took ([\d.]+) seconds", line)
        route_time_line = re.search(r"# Routing took ([\d.]+) seconds", line)
        total_time_line = re.search(r"The entire flow of VPR took ([\d.]+) seconds", line)
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
        elif pack_time_line:
            pack_time = float(pack_time_line.group(1))
        elif place_time_line:
            place_time = float(place_time_line.group(1))
        elif route_time_line:
            route_time = float(route_time_line.group(1))
        elif total_time_line:
            total_time = float(total_time_line.group(1))

    assert cpd > 0
    assert wl > 0
    assert pack_time > 0
    assert place_time > 0
    assert route_time > 0
    assert total_time > 0

    return cpd, wl, pack_time, place_time, route_time, total_time


def check_vpr_output(task_dir, out_file_name):
    circuits = os.listdir(task_dir)
    print(f"Circuits: {circuits}\n\n")

    data = [["Circuit", "Td", "WL", "Pack", "Place", "Route", "Total"]]
    for circuit in circuits:
        circuit_dir = os.path.join(task_dir, circuit, "common")
        vpr_out_file = os.path.join(circuit_dir, "vpr.out")

        if os.path.isfile(vpr_out_file):
            with open(vpr_out_file, "r") as file1:
                vpr_out_content = file1.read()

                circuit_name = circuit_dir.split("/")[-2]

                if not "VPR succeeded" in vpr_out_content:
                    print(f"{circuit_name} failed!")
                    continue
                cpd, wl, pa_time, pl_time, r_time, t_time = extract_circuit_info(vpr_out_content)
                data.append([f"{circuit_name}", f"{cpd:.2f}", f"{wl}", f"{pa_time}", f"{pl_time}", f"{r_time}", f"{t_time}"])

        else:
            print(f"Couldn't find {vpr_out_file}")

    with open(out_file_name, "w") as csv_file:
        csv_writer = csv.writer(csv_file, delimiter="\t")
        csv_writer.writerows(data)



def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task_dir", required=True, help="File that contains the actual results")
    parser.add_argument("--out_file_name", required=True, help="Name of the output file")

    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = getArgs()
    check_vpr_output(args.task_dir, args.out_file_name)
