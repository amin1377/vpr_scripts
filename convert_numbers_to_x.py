import csv
import os
import sys
import argparse


def convert_csv(src_path, dest_path, row_offset, col_offset):
    with open(src_path, "r", newline="") as infile:
        reader = csv.reader(infile)
        rows = list(reader)

    result = []
    for r_idx, row in enumerate(rows):
        new_row = []
        for c_idx, cell in enumerate(row):
            if r_idx >= row_offset and c_idx >= col_offset:
                stripped = cell.strip()
                try:
                    float(stripped)
                    new_row.append("x")
                except ValueError:
                    new_row.append(cell)
            else:
                new_row.append(cell)
        result.append(new_row)

    with open(dest_path, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.writer(outfile, lineterminator="\n")
        writer.writerows(result)


def main():
    parser = argparse.ArgumentParser(
        description="Convert numbers to 'x' in CSV files starting from a given offset."
    )
    parser.add_argument("src_dir", help="Source directory containing CSV files")
    parser.add_argument("dest_dir", help="Destination directory for output CSV files")
    parser.add_argument("--row-offset", type=int, default=0, help="Row offset (0-based)")
    parser.add_argument("--col-offset", type=int, default=0, help="Column offset (0-based)")
    args = parser.parse_args()

    os.makedirs(args.dest_dir, exist_ok=True)

    csv_files = [f for f in os.listdir(args.src_dir) if f.lower().endswith(".csv")]
    if not csv_files:
        print("No CSV files found in source directory.")
        sys.exit(0)

    for filename in csv_files:
        src_path = os.path.join(args.src_dir, filename)
        dest_path = os.path.join(args.dest_dir, filename)
        convert_csv(src_path, dest_path, args.row_offset, args.col_offset)
        print(f"Processed: {filename}")

    print(f"Done. {len(csv_files)} file(s) processed.")


if __name__ == "__main__":
    main()