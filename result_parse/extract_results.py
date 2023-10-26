import os
import re   
import argparse
import csv

def extract_circuit_info(contents):
    lines = contents.split("\n")
    
    cpd = -1
    wl = -1

    for line in lines:
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

    return cpd, wl


def check_vpr_output(task_dir, out_file_name):
    circuits = os.listdir(task_dir)
    print(f"Circuits: {circuits}\n\n")

    data = [["Circuit", "Td", "WL"]]
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
                cpd, wl = extract_circuit_info(vpr_out_content)
                data.append([f"{circuit_name}", f"{cpd:.2f}", f"{wl}"])

        else:
            print(f"Couldn't find {vpr_out_file}")

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
    check_vpr_output(args.task_dir, args.out_file_name)
