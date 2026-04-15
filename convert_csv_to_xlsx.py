import os
import sys
import csv
import argparse
import openpyxl


def csv_to_xlsx(src_path, dest_path):
    wb = openpyxl.Workbook()
    ws = wb.active

    with open(src_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            ws.append(row)

    wb.save(dest_path)


def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to XLSX.")
    parser.add_argument("src_dir", help="Source directory containing CSV files")
    parser.add_argument("dest_dir", help="Destination directory for XLSX files")
    args = parser.parse_args()

    os.makedirs(args.dest_dir, exist_ok=True)

    csv_files = [f for f in os.listdir(args.src_dir) if f.lower().endswith(".csv")]
    if not csv_files:
        print("No CSV files found.")
        sys.exit(0)

    for filename in csv_files:
        src_path = os.path.join(args.src_dir, filename)
        dest_name = os.path.splitext(filename)[0] + ".xlsx"
        dest_path = os.path.join(args.dest_dir, dest_name)
        csv_to_xlsx(src_path, dest_path)
        print(f"Converted: {filename} -> {dest_name}")

    print(f"Done. {len(csv_files)} file(s) converted.")


if __name__ == "__main__":
    main()