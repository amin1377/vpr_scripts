#!/usr/bin/env python3
"""
VPR Circuit Processor

This script processes multiple VPR circuits in parallel by:
1. Reading VPR command from packing.rpt files
2. Modifying the command to use --analytical_place --route --analysis
3. Setting up output directories with required files
4. Running the modified VPR commands

Usage:
    python vpr_processor.py --task_dir /path/to/tasks --output_dir /path/to/output --arch_dir /path/to/arch
"""

import os
import re
import shutil
import subprocess
import argparse
import logging
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, Optional


def setup_logging():
    """Configure logging for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('vpr_processor.log'),
            logging.StreamHandler()
        ]
    )


def find_circuits(task_dir: Path) -> List[str]:
    """
    Find all circuit directories in the task directory.
    
    Args:
        task_dir: Path to the task directory
        
    Returns:
        List of circuit names (directory names)
    """
    circuits = []
    if not task_dir.exists():
        raise FileNotFoundError(f"Task directory not found: {task_dir}")
    
    for item in task_dir.iterdir():
        if item.is_dir():
            circuits.append(item.name)
    
    logging.info(f"Found {len(circuits)} circuits: {circuits}")
    return circuits


def read_vpr_command(packing_rpt_path: Path) -> str:
    """
    Read VPR command from packing.rpt file.
    
    Args:
        packing_rpt_path: Path to the packing.rpt file
        
    Returns:
        The VPR command line as a string
        
    Raises:
        FileNotFoundError: If packing.rpt file doesn't exist
        ValueError: If VPR command line not found in file
    """
    if not packing_rpt_path.exists():
        raise FileNotFoundError(f"packing.rpt file not found: {packing_rpt_path}")
    
    try:
        with open(packing_rpt_path, 'r') as f:
            lines = f.readlines()
        
        # Find the line with VPR command
        for i, line in enumerate(lines):
            if "VPR was run with the following command-line:" in line:
                if i + 1 < len(lines):
                    command = lines[i + 1].strip()
                    logging.info(f"Found VPR command: {command}")
                    return command
                else:
                    raise ValueError("VPR command line not found after marker line")
        
        raise ValueError("VPR command marker line not found in packing.rpt")
    
    except Exception as e:
        raise ValueError(f"Error reading packing.rpt: {e}")


def modify_vpr_command(original_command: str) -> Tuple[str, str]:
    """
    Modify VPR command to replace --pack with --analytical_place --route --analysis.
    Also extract device size from the command.
    
    Args:
        original_command: Original VPR command string
        
    Returns:
        Tuple of (modified_command, device_size)
        
    Raises:
        ValueError: If --pack not found or device size not found
    """
    if "--pack" not in original_command:
        raise ValueError("--pack parameter not found in VPR command")
    
    # Replace --pack with new parameters
    modified_command = original_command.replace("--pack", "--analytical_place --route --analysis")
    
    # Extract device size (pattern: --device FPGA####)
    device_match = re.search(r'--device\s+FPGA(\d+)', original_command)
    if not device_match:
        raise ValueError("Device size not found in VPR command (expected --device FPGA####)")
    
    device_size = device_match.group(1)
    logging.info(f"Extracted device size: {device_size}")
    
    return modified_command, device_size


def update_vpr_command_arch_path(command: str) -> str:
    """
    Update the VPR command to use 'vpr.xml' as the second argument (architecture file).
    
    Args:
        command: VPR command string
        
    Returns:
        Modified command with vpr.xml as second argument
    """
    parts = command.split()
    if len(parts) < 2:
        raise ValueError("VPR command doesn't have enough arguments")
    
    # Replace the second argument (architecture file) with vpr.xml
    parts[1] = "vpr.xml"
    
    return " ".join(parts)


def setup_output_directory(circuit_name: str, output_dir: Path, task_dir: Path, 
                          arch_dir: Path, device_size: str) -> Path:
    """
    Set up output directory for a circuit with required files.
    
    Args:
        circuit_name: Name of the circuit
        output_dir: Base output directory
        task_dir: Task directory containing source files
        arch_dir: Architecture directory
        device_size: Device size extracted from VPR command
        
    Returns:
        Path to the created circuit output directory
        
    Raises:
        FileNotFoundError: If required files are not found
    """
    # Create output directory structure
    circuit_output_dir = output_dir / circuit_name / circuit_name
    circuit_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy .blif file
    blif_source = task_dir / circuit_name / circuit_name / f"{circuit_name}_post_synth.blif"
    if not blif_source.exists():
        raise FileNotFoundError(f"BLIF file not found: {blif_source}")
    
    blif_dest = circuit_output_dir / f"{circuit_name}_post_synth.blif"
    shutil.copy2(blif_source, blif_dest)
    logging.info(f"Copied BLIF file to: {blif_dest}")
    
    # Copy vpr.xml file
    vpr_xml_source = arch_dir / f"TURNKEY-FPGA{device_size}-2024Q3" / "LVT" / "WORST" / "vpr.xml"
    if not vpr_xml_source.exists():
        raise FileNotFoundError(f"VPR XML file not found: {vpr_xml_source}")
    
    vpr_xml_dest = circuit_output_dir / "vpr.xml"
    shutil.copy2(vpr_xml_source, vpr_xml_dest)
    logging.info(f"Copied VPR XML file to: {vpr_xml_dest}")
    
    return circuit_output_dir


def run_vpr_command(command: str, working_dir: Path) -> Tuple[bool, str]:
    """
    Run VPR command in the specified directory.
    
    Args:
        command: VPR command to run
        working_dir: Directory to run the command in
        
    Returns:
        Tuple of (success, output/error_message)
    """
    try:
        logging.info(f"Running VPR command in {working_dir}: {command}")
        
        result = subprocess.run(
            command.split(),
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            logging.info(f"VPR command completed successfully for {working_dir.name}")
            return True, "Success"
        else:
            error_msg = f"VPR command failed with return code {result.returncode}\nSTDERR: {result.stderr}"
            logging.error(error_msg)
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = "VPR command timed out after 1 hour"
        logging.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error running VPR command: {e}"
        logging.error(error_msg)
        return False, error_msg


def process_circuit(circuit_name: str, task_dir: Path, output_dir: Path, arch_dir: Path) -> Tuple[str, bool, str]:
    """
    Process a single circuit: read command, modify it, set up files, and run VPR.
    
    Args:
        circuit_name: Name of the circuit to process
        task_dir: Task directory
        output_dir: Output directory
        arch_dir: Architecture directory
        
    Returns:
        Tuple of (circuit_name, success, message)
    """
    try:
        logging.info(f"Processing circuit: {circuit_name}")
        
        # Read VPR command from packing.rpt
        packing_rpt_path = task_dir / circuit_name / circuit_name / "packing.rpt"
        original_command = read_vpr_command(packing_rpt_path)
        
        # Modify command and extract device size
        modified_command, device_size = modify_vpr_command(original_command)
        
        # Update command to use vpr.xml
        final_command = update_vpr_command_arch_path(modified_command)
        
        # Set up output directory with required files
        circuit_output_dir = setup_output_directory(
            circuit_name, output_dir, task_dir, arch_dir, device_size
        )
        
        # Run VPR command
        success, message = run_vpr_command(final_command, circuit_output_dir)
        
        return circuit_name, success, message
        
    except Exception as e:
        error_msg = f"Error processing circuit {circuit_name}: {e}"
        logging.error(error_msg)
        return circuit_name, False, error_msg


def main():
    """Main function to orchestrate the VPR circuit processing."""
    parser = argparse.ArgumentParser(description="Process VPR circuits in parallel")
    parser.add_argument("--task_dir", required=True, type=str, 
                       help="Directory containing circuit task directories")
    parser.add_argument("--output_dir", required=True, type=str,
                       help="Output directory for processed circuits")
    parser.add_argument("--arch_dir", required=True, type=str,
                       help="Architecture directory containing VPR XML files")
    parser.add_argument("--max_workers", type=int, default=4,
                       help="Maximum number of parallel processes (default: 4)")
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging()
    
    # Convert paths
    task_dir = Path(args.task_dir)
    output_dir = Path(args.output_dir)
    arch_dir = Path(args.arch_dir)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Find all circuits
        circuits = find_circuits(task_dir)
        
        if not circuits:
            logging.warning("No circuits found in task directory")
            return
        
        # Process circuits in parallel using separate processes
        logging.info(f"Starting parallel processing of {len(circuits)} circuits with {args.max_workers} processes")
        
        results = []
        with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
            # Submit all circuit processing tasks
            future_to_circuit = {
                executor.submit(process_circuit, circuit, task_dir, output_dir, arch_dir): circuit
                for circuit in circuits
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_circuit):
                circuit_name, success, message = future.result()
                results.append((circuit_name, success, message))
                
                if success:
                    logging.info(f"✓ {circuit_name}: {message}")
                else:
                    logging.error(f"✗ {circuit_name}: {message}")
        
        # Summary
        successful = sum(1 for _, success, _ in results if success)
        total = len(results)
        
        logging.info(f"\n=== PROCESSING SUMMARY ===")
        logging.info(f"Total circuits: {total}")
        logging.info(f"Successful: {successful}")
        logging.info(f"Failed: {total - successful}")
        
        if successful < total:
            logging.warning("Some circuits failed to process. Check the log for details.")
        else:
            logging.info("All circuits processed successfully!")
            
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())