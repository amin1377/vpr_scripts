import os
import shutil
import tarfile
import argparse

# Global list of names to search for in filenames
CIRCUITS = ["gsm_switch_stratixiv_arch_timing", "mes_noc_stratixiv_arch_timing", "dart_stratixiv_arch_timing", "denoise_stratixiv_arch_timing", "sparcT2_core_stratixiv_arch_timing", \
            "cholesky_bdti_stratixiv_arch_timing", "minres_stratixiv_arch_timing", "stap_qrd_stratixiv_arch_timing", "openCV_stratixiv_arch_timing", "bitonic_mesh_stratixiv_arch_timing", \
            "segmentation_stratixiv_arch_timing", "SLAM_spheric_stratixiv_arch_timing", "des90_stratixiv_arch_timing", "neuron_stratixiv_arch_timing", "sparcT1_core_stratixiv_arch_timing", \
            "stereo_vision_stratixiv_arch_timing", "cholesky_mc_stratixiv_arch_timing", "directrf_stratixiv_arch_timing", "bitcoin_miner_stratixiv_arch_timing", "LU230_stratixiv_arch_timing", \
            "sparcT1_chip2_stratixiv_arch_timing", "LU_Network_stratixiv_arch_timing"]

CIRCUITS = ["carpat_stratixiv_arch_timing", "CH_DFSIN_stratixiv_arch_timing", "CHERI_stratixiv_arch_timing", "fir_cascade_stratixiv_arch_timing", "jacobi_stratixiv_arch_timing", \
            "JPEG_stratixiv_arch_timing", "leon2_stratixiv_arch_timing", "leon3mp_stratixiv_arch_timing", "MCML_stratixiv_arch_timing", "MMM_stratixiv_arch_timing", \
            "radar20_stratixiv_arch_timing", "random_stratixiv_arch_timing", "Reed_Solomon_stratixiv_arch_timing", "smithwaterman_stratixiv_arch_timing", "stap_steering_stratixiv_arch_timing", \
            "sudoku_check_stratixiv_arch_timing", "SURF_desc_stratixiv_arch_timing", "ucsb_152_tap_fir_stratixiv_arch_timing", "uoft_raytracer_stratixiv_arch_timing", \
            "wb_conmax_stratixiv_arch_timing", "picosoc_stratixiv_arch_timing", "murax_stratixiv_arch_timing", "EKF-SLAM_Jacobians_stratixiv_arch_timing"]

def get_arguments():
    """
    Parses and returns command-line arguments.
    :return: Parsed arguments containing input_dir and output_dir
    """
    parser = argparse.ArgumentParser(description="Filter files and compress them with maximum compression.")
    parser.add_argument("input_dir", help="Directory to search for matching files")
    parser.add_argument("output_dir", help="Directory where matching files will be copied")
    return parser.parse_args()

def filter_and_compress(input_dir, output_dir):
    """
    Searches for files containing any of the specified names in their filenames within input_dir.
    Moves them to output_dir and compresses the output_dir into a `.tar.xz` archive with maximum compression.

    :param input_dir: Directory to search for matching files.
    :param output_dir: Directory where matching files will be copied.
    """
    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist.")
        return

    # Create the output directory if it does not exist
    os.makedirs(output_dir, exist_ok=True)

    # Search and copy matching files
    for root, _, files in os.walk(input_dir):
        for file in files:
            if any(name in file for name in CIRCUITS):
                source_file = os.path.join(root, file)
                destination_file = os.path.join(output_dir, file)
                shutil.copy2(source_file, destination_file)  # Preserve metadata

    # Compress the directory using .tar.xz (maximum compression)
    tar_filename = f"{output_dir}.tar.xz"
    with tarfile.open(tar_filename, "w:xz") as tarf:
        tarf.add(output_dir, arcname=os.path.basename(output_dir))

    print(f"Compression completed. Output TAR.XZ: {tar_filename}")

if __name__ == "__main__":
    args = get_arguments()
    filter_and_compress(args.input_dir, args.output_dir)
