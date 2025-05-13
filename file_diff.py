import os
import filecmp
import csv

# Paths to the two root directories
dir1 = "/home/amohaghegh/release_test/aurora2/tests/testsuite_logfiles__marketing_12_MAY_2025_14_18_21"
dir2 = "/dsoft/amohaghegh/aurora_2025_1/testsuit_logfiles"

# Output file
output_tsv = "comparison_results.tsv"

# Get list of subdirectories (only top-level)
subdirs1 = [d for d in os.listdir(dir1) if os.path.isdir(os.path.join(dir1, d))]

results = []

for subdir in subdirs1:
    path1 = os.path.join(dir1, subdir, subdir, f"{subdir}_post_synth.blif")
    path2 = os.path.join(dir2, subdir, subdir, f"{subdir}_post_synth.blif")

    assert os.path.exists(path1)
    assert os.path.exists(path2)

    different = not filecmp.cmp(path1, path2, shallow=False)

    results.append([subdir, "yes" if different else "no"])

# Write to TSV
with open(output_tsv, "w", newline="") as f:
    writer = csv.writer(f, delimiter='\t')
    writer.writerow(["subdirectory", "different"])
    writer.writerows(results)

print(f"Comparison complete. Results written to {output_tsv}")
