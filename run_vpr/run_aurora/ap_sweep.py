#!/usr/bin/env python3
"""
AP Parameter Sweep Script for VPR / Aurora

Sweeps over VPR analytical-placement parameter combinations across one or more
benchmark sets, using work-stealing parallelism to keep all cores busy.

A new circuit (even from a different parameter set) is launched as soon as any
worker core becomes free, so a slow circuit never stalls the whole experiment.

Directory structure created
───────────────────────────
    <output_dir>/
        sweep.log                       # main log (all events)
        sweep_summary.csv               # one row per completed job
        <param_set_name>/
            params.json                 # full parameter dict for this set
            <benchmark_name>/
                <circuit_name>/
                    cmd.txt             # exact VPR command that was run
                    vpr.out             # VPR stdout
                    vpr.err             # VPR stderr

Customising the sweep
─────────────────────
Edit SWEEP_GRID near the top of this file.  Each key is a VPR flag name
(without the leading --), and each value is the list of values to try.
All combinations (Cartesian product) are generated automatically.

To run a subset, use --param_sets or --circuits on the CLI.
To add a parameter dimension, just add a new entry to SWEEP_GRID.
To fix a parameter at a single value, give it a one-element list.
Comment out any row to let VPR use its built-in default.

Usage examples
──────────────
    # Full sweep, 20 parallel workers
    python ap_sweep.py \\
        --vpr_binary /path/to/vpr \\
        --output_dir /results/sweep_v1 \\
        --resource_dir /data/blif_sdc \\
        --device_data_dir /data/device_data \\
        --benchmark titan23:/data/titan23 mcnc:/data/mcnc \\
        --max_workers 20

    # Dry run: see what jobs would be launched without running them
    python ap_sweep.py ... --dry_run

    # Resume a partially-completed sweep (skip existing vpr.out files)
    python ap_sweep.py ... --skip_completed

    # Only run specific circuits / parameter sets
    python ap_sweep.py ... --circuits des bgm --param_sets 0003__ATT0.5__APLbip__IN0.5
"""

import csv
import itertools
import json
import logging
import re
import shutil
import subprocess
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# SWEEP CONFIGURATION
#
# Edit this section to add, remove, or adjust the sweep dimensions.
# Keys must match VPR CLI flag names (without the leading --).
# ─────────────────────────────────────────────────────────────────────────────

SWEEP_GRID: Dict[str, List[Any]] = {
    # ── Global-placer timing/wirelength trade-off ────────────────────────────
    # 0.0 = minimise HPWL only, 1.0 = minimise timing only.  Default: 0.5
    # Suggested range: [0.0 … 1.0], step 0.25 (5 values)
    "ap_timing_tradeoff": [0.0, 0.25, 0.5, 0.75, 1.0],

    # ── Partial-legaliser algorithm ──────────────────────────────────────────
    # bipartitioning: shrinks over-dense windows by binary partitioning.
    # flow-based:     flows atoms from over-filled to under-filled regions.
    "ap_partial_legalizer": ["bipartitioning", "flow-based"],

    # ── Detailed-placer (annealer) effort ────────────────────────────────────
    # Moves per temperature step = inner_num × N^(4/3).  Default: 0.5
    # Lower → faster but lower quality; higher → slower but better quality.
    # Suggested range: [0.3 … 1.5], step ~0.35 (3–4 values)
    "inner_num": [0.3, 0.5, 1.0],

    # ── NEWLY EXPOSED PARAMETERS ─────────────────────────────────────────────
    # Each block below is commented out by default.  Enabling one at a time
    # is recommended for a first sweep; enabling multiple simultaneously
    # multiplies the total job count.

    # ── Global-placer convergence gap ────────────────────────────────────────
    # Stops the outer solver-legalizer loop when (UB_HPWL - LB_HPWL)/UB < gap.
    # Tighter → more iterations, better quality; looser → faster.  Default: 0.01
    # Suggested range: [0.002 … 0.02], 4 values → ×4 jobs
    "ap_convergence_gap": [0.002, 0.005, 0.01, 0.02],

    # ── B2B anchor-weight multiplier ─────────────────────────────────────────
    # w = ap_anchor_weight_mult * exp(iter / ap_anchor_weight_exp_fac)
    # Smaller → weaker early anchors (more spreading freedom).  Default: 0.01
    # Suggested range: [0.003 … 0.03], 3 values → ×3 jobs
    "ap_anchor_weight_mult": [0.003, 0.01, 0.03],

    # ── B2B anchor-weight exponential growth factor ───────────────────────────
    # Larger → slower anchor growth (solver stays "loose" longer).  Default: 5.0
    # Suggested range: [3.0 … 8.0], 3 values → ×3 jobs
    # "ap_anchor_weight_exp_fac": [3.0, 5.0, 8.0],

    # ── B2B timing objective scale factor ────────────────────────────────────
    # Effective timing weight = ap_timing_tradeoff × net_w × timing_slope × (1+crit)
    # Interacts multiplicatively with ap_timing_tradeoff.  Default: 0.75
    # Suggested range: [0.3 … 1.5], 4 values → ×4 jobs (×20 with ap_timing_tradeoff)
    # "ap_timing_slope_fac": [0.3, 0.5, 0.75, 1.0, 1.5],

    # ── B2B inner bound-update iterations ────────────────────────────────────
    # Higher → better per-outer-iter quality, but longer solver time.  Default: 24
    # Suggested values: 3 → ×3 jobs
    # "ap_b2b_max_bound_updates": [12, 24, 48],

    # ── Flow-based legalizer neighbour radius (bin hops) ─────────────────────
    # Larger → atoms can flow farther per iteration; helps sparse hetero tiles.
    # Default: 4.  Suggested: 3 values → ×3 jobs
    # "ap_flow_max_neighbor_dist": [4, 8, 12],

    # ── Bi-partitioning legalizer cluster gap (bins) ─────────────────────────
    # Max gap between overfilled bins merged into one spreading window.
    # Default: 2.  Suggested: 3 values → ×3 jobs
    # "ap_bipart_max_cluster_gap": [1, 2, 4],

    # ── High-fanout threshold ────────────────────────────────────────────────
    # Nets with more pins than this are ignored by the analytical solver,
    # which keeps solver matrices sparse.  Default: 256
    # Uncomment to include this dimension in the sweep (×3 jobs).
    # "ap_high_fanout_threshold": [128, 256, 512],

    # ── Analytical solver algorithm ──────────────────────────────────────────
    # lp-b2b:   Linear programming with Bound-to-Bound net model (default).
    # qp-hybrid: Quadratic programming with hybrid clique/star net model.
    # Uncomment to compare solvers (×2 jobs).
    # "ap_analytical_solver": ["lp-b2b", "qp-hybrid"],
}

# Flags added to every VPR call regardless of which parameter set is being run.
# These select the AP + routing + analysis stages.
COMMON_AP_FLAGS: List[str] = [
    "--analytical_place", "on",
    "--route",
    "--analysis",
]

# ─────────────────────────────────────────────────────────────────────────────
# Short labels used when constructing directory names from parameter values
# ─────────────────────────────────────────────────────────────────────────────

_SHORT_LABEL: Dict[str, str] = {
    "ap_timing_tradeoff":           "ATT",
    "ap_partial_legalizer":         "APL",
    "inner_num":                    "IN",
    "ap_high_fanout_threshold":     "HFT",
    "ap_analytical_solver":         "AAS",
    "ap_full_legalizer":            "AFL",
    "ap_detailed_placer":           "ADP",
    "timing_tradeoff":              "TT",
    "anneal_auto_init_t_scale":     "ATIS",
    # newly exposed AP parameters
    "ap_convergence_gap":           "CG",
    "ap_anchor_weight_mult":        "AWM",
    "ap_anchor_weight_exp_fac":     "AWE",
    "ap_timing_slope_fac":          "TSF",
    "ap_b2b_max_bound_updates":     "MBU",
    "ap_flow_max_neighbor_dist":    "FND",
    "ap_bipart_max_cluster_gap":    "BCG",
}

_VALUE_ABBREV: Dict[str, str] = {
    "bipartitioning": "bip",
    "flow-based":     "flow",
    "none":           "none",
    "appack":         "app",
    "flat-recon":     "frc",
    "annealer":       "ann",
    "lp-b2b":         "lpb",
    "qp-hybrid":      "qph",
    "identity":       "id",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JobSpec:
    """Everything needed to execute one (parameter_set × circuit) job."""
    param_set_name: str
    param_set: Dict[str, Any]
    benchmark_name: str
    circuit_name: str
    vpr_binary: Path
    task_dir: Path
    output_dir: Path
    resource_dir: Path
    device_data_dir: Path
    timeout_seconds: int
    seed: int
    extra_vpr_args: List[str]


@dataclass
class JobResult:
    """Return value from a completed (or failed) job."""
    param_set_name: str
    benchmark_name: str
    circuit_name: str
    success: bool
    message: str
    runtime_seconds: float = 0.0
    cpd_ns: Optional[float] = None
    routed_wirelength: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_param_set_dir_name(idx: int, param_set: Dict[str, Any]) -> str:
    """
    Build a human-readable, filesystem-safe directory name for a parameter set.

    Example: 0003__ATT0.5__APLbip__IN0.5
    """
    parts = [f"{idx:04d}"]
    for k, v in param_set.items():
        label = _SHORT_LABEL.get(k, k[:4].upper())
        if isinstance(v, float):
            # e.g. 0.500 → "0.5", 0.250 → "0.25", 1.000 → "1"
            val_str = f"{v:.3f}".rstrip("0").rstrip(".")
        else:
            val_str = _VALUE_ABBREV.get(str(v), str(v).replace("-", "").replace("_", ""))
        parts.append(f"{label}{val_str}")
    return "__".join(parts)


def build_param_sets() -> List[Tuple[str, Dict[str, Any]]]:
    """Expand SWEEP_GRID into a list of (directory_name, param_dict) pairs."""
    keys = list(SWEEP_GRID.keys())
    values = list(SWEEP_GRID.values())
    result = []
    for idx, combo in enumerate(itertools.product(*values)):
        param_set = dict(zip(keys, combo))
        name = _make_param_set_dir_name(idx, param_set)
        result.append((name, param_set))
    return result


def find_circuits(task_dir: Path) -> List[str]:
    """Return sorted circuit names (subdirectory names) in a benchmark task directory."""
    if not task_dir.exists():
        raise FileNotFoundError(f"Task directory not found: {task_dir}")
    circuits = sorted(p.name for p in task_dir.iterdir() if p.is_dir())
    if not circuits:
        raise ValueError(f"No circuit directories found in {task_dir}")
    return circuits


def read_device_size(packing_rpt: Path) -> str:
    if not packing_rpt.exists():
        raise FileNotFoundError(f"packing.rpt not found: {packing_rpt}")
    text = packing_rpt.read_text()
    m = re.search(r'--device\s+FPGA(\d+)', text)
    if not m:
        raise ValueError(f"Could not find '--device FPGA####' in {packing_rpt}")
    return m.group(1)


def param_set_to_vpr_args(param_set: Dict[str, Any]) -> List[str]:
    """Convert {flag: value} dict to ['--flag', 'value', ...] list."""
    args: List[str] = []
    for k, v in param_set.items():
        args.extend([f"--{k}", str(v)])
    return args


def extract_metrics(vpr_out: Path) -> Tuple[Optional[float], Optional[int]]:
    """Parse critical-path delay (ns) and total wirelength from vpr.out."""
    if not vpr_out.exists():
        return None, None
    text = vpr_out.read_text(errors="replace")
    cpd = None
    wl = None
    m = re.search(r'Final critical path delay.*?:\s*([\d.]+)\s*ns', text)
    if m:
        cpd = float(m.group(1))
    m = re.search(r'Total wirelength:\s*(\d+)', text)
    if m:
        wl = int(m.group(1))
    return cpd, wl


def already_completed(circuit_out: Path) -> bool:
    """Return True if the circuit was successfully run (archived or uncompressed)."""
    # Compressed circuits count as done
    archive = circuit_out.parent / (circuit_out.name + ".tar.gz")
    if archive.exists():
        return True
    vpr_out = circuit_out / "vpr.out"
    if not vpr_out.exists():
        return False
    try:
        tail = vpr_out.read_text(errors="replace")[-4096:]
        return "VPR succeeded" in tail or "vpr_exit_code: 0" in tail
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Post-processing: metric extraction + compression
# ─────────────────────────────────────────────────────────────────────────────

def load_result_config(config_path: Path) -> Dict[str, List[Tuple[str, str]]]:
    """
    Parse a config.txt in the format used by extract_results.py:
        metric_name;output_filename;regex_pattern[;colorscale]
    Returns {filename: [(metric_name, pattern), ...]}.
    """
    entries: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            if len(parts) >= 3:
                entries[parts[1].strip()].append((parts[0].strip(), parts[2].strip()))
    return dict(entries)


def extract_circuit_metrics(
    circuit_dir: Path,
    config_entries: Dict[str, List[Tuple[str, str]]],
) -> Dict[str, Optional[str]]:
    """
    Extract all metrics from the log files in one circuit directory.
    Supports regular regex patterns and CONTEXT:ctx>>>val patterns.
    """
    metrics: Dict[str, Optional[str]] = {}
    for _fname, patterns in config_entries.items():
        for metric_name, _ in patterns:
            metrics.setdefault(metric_name, None)

    for filename, patterns in config_entries.items():
        path = circuit_dir / filename
        try:
            lines = path.read_text(errors="replace").splitlines()
        except (FileNotFoundError, OSError):
            continue

        # Split into regular and context-aware patterns
        regular = [(n, p) for n, p in patterns if not p.startswith("CONTEXT:")]
        context_raw = [(n, p[8:]) for n, p in patterns if p.startswith("CONTEXT:")]
        ctx_groups: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for name, body in context_raw:
            if ">>>" in body:
                ctx_pat, val_pat = body.split(">>>", 1)
                ctx_groups[ctx_pat.strip()].append((name, val_pat.strip()))
        sorted_ctxs = sorted(ctx_groups, key=len, reverse=True)

        current_ctx: Optional[str] = None
        for line in lines:
            s = line.strip()
            # Update active context
            for ctx_pat in sorted_ctxs:
                if re.search(ctx_pat, s):
                    current_ctx = ctx_pat
                    break
            # Context-aware matches
            if current_ctx and current_ctx in ctx_groups:
                for name, val_pat in ctx_groups[current_ctx]:
                    if metrics.get(name) is not None:
                        continue
                    m = re.search(val_pat, s)
                    if m:
                        metrics[name] = m.group(1).strip()
            # Regular matches
            for name, pattern in regular:
                if metrics.get(name) is not None:
                    continue
                m = re.search(pattern, s)
                if m:
                    metrics[name] = m.group(1).strip()

    return metrics


def parse_and_compress_benchmark(
    bench_dir: Path,
    config_entries: Dict[str, List[Tuple[str, str]]],
    compress: bool,
) -> None:
    """
    After all circuits in one (param_set, benchmark) pair have finished:
      1. Parse metrics from every circuit's log files → <bench_dir>/results.csv
      2. If compress=True, tar.gz each circuit directory and remove the original.
    """
    # Collect metric names in config order (de-duplicated, preserving order)
    metric_names = [name for patterns in config_entries.values() for name, _ in patterns]
    seen: set = set()
    ordered_metrics = [n for n in metric_names if not (n in seen or seen.add(n))]  # type: ignore[func-returns-value]

    rows = []
    for circuit_dir in sorted(bench_dir.iterdir()):
        if not circuit_dir.is_dir():
            continue
        metrics = extract_circuit_metrics(circuit_dir, config_entries)
        row: Dict[str, Any] = {"circuit": circuit_dir.name}
        row.update({k: metrics.get(k) for k in ordered_metrics})
        rows.append(row)

    if rows:
        csv_path = bench_dir / "results.csv"
        fieldnames = ["circuit"] + ordered_metrics
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        logging.info(f"  Results parsed: {len(rows)} circuits → {csv_path}")

    if not compress:
        return

    for circuit_dir in sorted(bench_dir.iterdir()):
        if not circuit_dir.is_dir():
            continue
        archive = bench_dir / (circuit_dir.name + ".tar.gz")
        try:
            subprocess.run(
                ["tar", "-czf", str(archive), "-C", str(bench_dir), circuit_dir.name],
                check=True,
                capture_output=True,
            )
            shutil.rmtree(circuit_dir)
            logging.info(f"  Archived: {archive.relative_to(bench_dir.parent.parent)}")
        except subprocess.CalledProcessError as exc:
            logging.error(
                f"  tar failed for {circuit_dir}: "
                f"{exc.stderr.decode(errors='replace').strip()}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Worker function (executed in a separate process)
# ─────────────────────────────────────────────────────────────────────────────

def run_job(job: JobSpec) -> JobResult:
    """
    Run a single VPR invocation.

    This function is pickled and sent to a worker process by ProcessPoolExecutor,
    so it must be a module-level function and all arguments must be picklable.
    All logging goes via the returned JobResult — worker processes do not write
    to the main log.
    """
    import time

    t0 = time.time()

    def _fail(msg: str) -> JobResult:
        return JobResult(
            param_set_name=job.param_set_name,
            benchmark_name=job.benchmark_name,
            circuit_name=job.circuit_name,
            success=False,
            message=msg,
            runtime_seconds=time.time() - t0,
        )

    try:
        packing_rpt = (
            job.task_dir / job.circuit_name / job.circuit_name / "packing.rpt"
        )
        device_size = read_device_size(packing_rpt)

        circuit_out = (
            job.output_dir
            / job.param_set_name
            / job.benchmark_name
            / job.circuit_name
        )
        circuit_out.mkdir(parents=True, exist_ok=True)

        # Device-data paths (same layout as run.py template)
        timing_corner = (
            job.device_data_dir
            / f"TURNKEY-FPGA{device_size}"
            / "LVT"
            / "SSPG_0P72_125C"
        )
        vpr_xml        = timing_corner / "vpr.xml"
        router_lah     = timing_corner / "router_lookahead.bin"
        sb_maps        = job.device_data_dir / f"TURNKEY-FPGA{device_size}" / "aurora" / "SB_MAPS.yml"
        sb_templates   = timing_corner / "CSV"
        blif           = job.resource_dir / f"{job.circuit_name}_post_synth.blif"
        sdc            = job.resource_dir / f"{job.circuit_name}.sdc"

        # Base command (mirrors run.py)
        cmd: List[str] = [
            str(job.vpr_binary),
            str(vpr_xml),
            str(blif),
            "--device",                                  f"FPGA{device_size}",
            "--target_ext_pin_util",                     "clb:0.8,1",
            "--timing_analysis",                         "on",
            "--constant_net_method",                     "route",
            "--clock_modeling",                          "ideal",
            "--exit_before_pack",                        "off",
            "--circuit_format",                          "eblif",
            "--sdc_file",                                str(sdc),
            "--absorb_buffer_luts",                      "off",
            "--route_chan_width",                         "160",
            "--flat_routing",                            "on",
            "--max_router_iterations",                   "200",
            "--routing_failure_predictor",               "off",
            "--gen_post_synthesis_netlist",              "on",
            "--post_synth_netlist_unconn_inputs",        "gnd",
            "--post_synth_netlist_unconn_outputs",       "unconnected",
            "--timing_report_npaths",                    "100",
            "--timing_report_detail",                    "detailed",
            "--generate_rr_node_overuse_report",         "on",
            "--allow_dangling_combinational_nodes",      "on",
            "--router_initial_acc_cost_chan_congestion_weight", "0.0",
            "--sb_maps",                                 str(sb_maps),
            "--sb_templates",                            str(sb_templates),
            "--annotated_rr_graph",                      "on",
            "--seed",                                    str(job.seed),
            "--analytical_place",
            "--route",
            "--analysis",
        ]

        # AP stage flags (always present)
        cmd.extend(COMMON_AP_FLAGS)

        # This run's sweep parameters
        cmd.extend(param_set_to_vpr_args(job.param_set))

        # Any extra user-supplied args
        cmd.extend(job.extra_vpr_args)

        # Save the exact command for later reproducibility / debugging
        (circuit_out / "cmd.txt").write_text(" \\\n    ".join(cmd) + "\n")

        result = subprocess.run(
            cmd,
            cwd=circuit_out,
            capture_output=True,
            text=True,
            timeout=job.timeout_seconds,
        )

        (circuit_out / "vpr.out").write_text(result.stdout)
        (circuit_out / "vpr.err").write_text(result.stderr)

        elapsed = time.time() - t0

        if result.returncode != 0:
            return _fail(f"VPR exited with code {result.returncode}")

        cpd, wl = extract_metrics(circuit_out / "vpr.out")
        return JobResult(
            param_set_name=job.param_set_name,
            benchmark_name=job.benchmark_name,
            circuit_name=job.circuit_name,
            success=True,
            message="OK",
            runtime_seconds=elapsed,
            cpd_ns=cpd,
            routed_wirelength=wl,
        )

    except subprocess.TimeoutExpired:
        return _fail(f"Timed out after {job.timeout_seconds}s")
    except Exception as exc:
        return _fail(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# CSV summary writer (called from the main process only — no race conditions)
# ─────────────────────────────────────────────────────────────────────────────

def append_csv_row(csv_path: Path, result: JobResult) -> None:
    row = asdict(result)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def read_options():
    parser = ArgumentParser(
        prog="ap_sweep.py",
        description=__doc__,
        formatter_class=RawDescriptionHelpFormatter,
    )

    # ── Required arguments ───────────────────────────────────────────────────
    req = parser.add_argument_group("required arguments")

    req.add_argument(
        "--vpr_binary",
        required=True,
        type=Path,
        metavar="PATH",
        help="Path to the VPR executable (e.g. /build/vpr/vpr).",
    )
    req.add_argument(
        "--output_dir",
        required=True,
        type=Path,
        metavar="DIR",
        help=(
            "Root directory for all results.  Created if it does not exist.  "
            "One sub-directory is created per parameter set, and inside that, "
            "one sub-directory per benchmark, then per circuit."
        ),
    )
    req.add_argument(
        "--benchmark_names",
        required=True,
        nargs="+",
        metavar="NAME",
        help=(
            "Names of the benchmarks to sweep (e.g. marketing koios).  "
            "Each name must correspond to a sub-directory of both --task_dir "
            "and --resource_dir."
        ),
    )
    req.add_argument(
        "--task_dir",
        required=True,
        type=Path,
        metavar="DIR",
        help=(
            "Root directory containing one sub-directory per benchmark.  "
            "Each benchmark sub-directory must follow the run.py layout: "
            "<task_dir>/<benchmark>/<circuit>/<circuit>/packing.rpt"
        ),
    )
    req.add_argument(
        "--resource_dir",
        required=True,
        type=Path,
        metavar="DIR",
        help=(
            "Root directory containing one sub-directory per benchmark.  "
            "Each benchmark sub-directory must contain the packed netlists and "
            "timing constraints: <circuit>_post_synth.blif and <circuit>.sdc."
        ),
    )
    req.add_argument(
        "--device_data_dir",
        required=True,
        type=Path,
        metavar="DIR",
        help=(
            "Device-data root.  Must contain TURNKEY-FPGA<size>/LVT/SSPG_0P72_125C/ "
            "sub-trees with vpr.xml, router_lookahead.bin, and CSV/ templates."
        ),
    )

    # ── Parallelism & limits ─────────────────────────────────────────────────
    run = parser.add_argument_group("run control")

    run.add_argument(
        "--max_workers",
        type=int,
        default=20,
        metavar="N",
        help=(
            "Maximum number of VPR processes to run in parallel.  "
            "Jobs are dispatched using work-stealing, so a free core will "
            "pick up the next waiting job regardless of which parameter set it "
            "belongs to.  Default: %(default)s."
        ),
    )
    run.add_argument(
        "--timeout",
        type=int,
        default=7200,
        metavar="SECONDS",
        help=(
            "Per-circuit wall-clock timeout in seconds.  A circuit that exceeds "
            "this limit is marked as failed and the next job is started immediately. "
            "Default: %(default)s (2 hours)."
        ),
    )
    run.add_argument(
        "--seed",
        type=int,
        default=1,
        metavar="N",
        help="VPR random seed passed via --seed.  Default: %(default)s.",
    )

    # ── Filtering ────────────────────────────────────────────────────────────
    filt = parser.add_argument_group("filtering (restrict the sweep without editing SWEEP_GRID)")

    filt.add_argument(
        "--circuits",
        nargs="+",
        metavar="NAME",
        help=(
            "Run only the listed circuit names (applies to every benchmark). "
            "If omitted, all circuits found in each benchmark directory are used."
        ),
    )
    filt.add_argument(
        "--param_sets",
        nargs="+",
        metavar="NAME",
        help=(
            "Run only the listed parameter-set directory names.  Use --dry_run "
            "first to see the full list of generated names."
        ),
    )
    filt.add_argument(
        "--skip_completed",
        action="store_true",
        help=(
            "Skip any (param_set, benchmark, circuit) triple whose output "
            "directory already contains a successful vpr.out.  "
            "Useful for resuming a partially-completed sweep."
        ),
    )

    # ── Misc ─────────────────────────────────────────────────────────────────
    misc = parser.add_argument_group("miscellaneous")

    misc.add_argument(
        "--extra_vpr_args",
        type=str,
        default="",
        metavar="ARGS",
        help=(
            "Extra VPR arguments appended to every invocation (space-separated). "
            "These come after the sweep parameters, so they can override them. "
            "Example: --extra_vpr_args '--timing_report_npaths 200'"
        ),
    )
    misc.add_argument(
        "--log_file",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Path for the main log file.  "
            "Default: <output_dir>/sweep.log."
        ),
    )
    misc.add_argument(
        "--dry_run",
        action="store_true",
        help=(
            "Print a summary of all jobs that would be launched (total count, "
            "estimated compute time, first/last 10 job names) without running "
            "anything.  Useful for sanity-checking the sweep before committing."
        ),
    )
    misc.add_argument(
        "--result_config",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Path to a config.txt in the extract_results.py format "
            "(metric_name;filename;regex).  When provided, after all circuits "
            "for a parameter set finish, metrics are extracted from each circuit's "
            "log files and written to <param_set>/results.csv.  The circuit "
            "directories are then compressed to .tar.gz to save storage "
            "(disable with --no_compress)."
        ),
    )
    misc.add_argument(
        "--no_compress",
        action="store_true",
        help=(
            "Parse metrics (--result_config required) but do NOT compress circuit "
            "directories.  Useful when you want results.csv but still need the "
            "raw log files accessible without extracting an archive."
        ),
    )

    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(log_file: Path) -> None:
    fmt = "%(asctime)s %(levelname)-8s %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = read_options()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    log_file = args.log_file or (output_dir / "sweep.log")
    setup_logging(log_file)

    # ── Load result config (optional) ────────────────────────────────────────
    config_entries: Dict[str, List[Tuple[str, str]]] = {}
    if args.result_config:
        if not args.result_config.exists():
            logging.error(f"--result_config file not found: {args.result_config}")
            return 1
        config_entries = load_result_config(args.result_config)
        logging.info(
            f"Result config: {args.result_config} "
            f"({sum(len(v) for v in config_entries.values())} metrics across "
            f"{len(config_entries)} file(s))"
        )

    # ── Validate benchmark roots and build per-benchmark task/resource dirs ──
    task_dir_root: Path = args.task_dir
    resource_dir_root: Path = args.resource_dir

    benchmark_sets: Dict[str, Path] = {}     # name → task subdir
    benchmark_res:  Dict[str, Path] = {}     # name → resource subdir

    for bname in args.benchmark_names:
        t = task_dir_root / bname
        r = resource_dir_root / bname
        missing = [str(p) for p in (t, r) if not p.exists()]
        if missing:
            logging.error(
                f"Benchmark '{bname}': missing directories: {', '.join(missing)}"
            )
            return 1
        benchmark_sets[bname] = t
        benchmark_res[bname]  = r

    # ── Build parameter sets ──────────────────────────────────────────────────
    all_param_sets = build_param_sets()
    logging.info(
        f"SWEEP_GRID → {len(all_param_sets)} parameter sets "
        f"from {[f'{k}({len(v)})' for k, v in SWEEP_GRID.items()]}"
    )

    if args.param_sets:
        keep = set(args.param_sets)
        all_param_sets = [(n, p) for n, p in all_param_sets if n in keep]
        if not all_param_sets:
            logging.error(
                "No matching parameter sets after --param_sets filter. "
                "Use --dry_run to see available names."
            )
            return 1
        logging.info(f"Filtered to {len(all_param_sets)} parameter set(s).")

    # Write params.json for every parameter set now (from the main process)
    # so worker processes never race to create it.
    for ps_name, ps_dict in all_param_sets:
        ps_dir = output_dir / ps_name
        ps_dir.mkdir(parents=True, exist_ok=True)
        params_json = ps_dir / "params.json"
        if not params_json.exists():
            params_json.write_text(json.dumps(ps_dict, indent=2))

    # ── Discover circuits and build job list ──────────────────────────────────
    extra_vpr_args = args.extra_vpr_args.split() if args.extra_vpr_args else []
    jobs: List[JobSpec] = []

    for bname, bmark_task_dir in benchmark_sets.items():
        try:
            circuits = find_circuits(bmark_task_dir)
        except (FileNotFoundError, ValueError) as exc:
            logging.error(str(exc))
            return 1

        if args.circuits:
            allowed = set(args.circuits)
            circuits = [c for c in circuits if c in allowed]
            if not circuits:
                logging.warning(
                    f"No matching circuits in benchmark '{bname}' after "
                    f"--circuits filter — skipping."
                )
                continue

        logging.info(f"Benchmark '{bname}': {len(circuits)} circuit(s)")

        for ps_name, ps_dict in all_param_sets:
            for circuit in circuits:
                circuit_out = output_dir / ps_name / bname / circuit
                if args.skip_completed and already_completed(circuit_out):
                    logging.info(
                        f"SKIP (already done): {ps_name}/{bname}/{circuit}"
                    )
                    continue
                jobs.append(
                    JobSpec(
                        param_set_name=ps_name,
                        param_set=ps_dict.copy(),
                        benchmark_name=bname,
                        circuit_name=circuit,
                        vpr_binary=args.vpr_binary,
                        task_dir=bmark_task_dir,
                        output_dir=output_dir,
                        resource_dir=benchmark_res[bname],
                        device_data_dir=args.device_data_dir,
                        timeout_seconds=args.timeout,
                        seed=args.seed,
                        extra_vpr_args=extra_vpr_args,
                    )
                )

    total = len(jobs)

    if total == 0:
        logging.warning("No jobs to run (all filtered or already completed).")
        return 0

    # ── Per-(param_set, benchmark) pending count for post-processing trigger ──
    ps_bench_pending: Dict[Tuple[str, str], int] = defaultdict(int)
    for job in jobs:
        ps_bench_pending[(job.param_set_name, job.benchmark_name)] += 1

    # If --skip_completed left some (ps, bench) pairs with 0 remaining jobs
    # (all circuits already done but not yet parsed/compressed), handle them now.
    if config_entries:
        all_ps_bench = {
            (ps_name, bname)
            for ps_name, _ in all_param_sets
            for bname in benchmark_sets
        }
        already_done = all_ps_bench - set(ps_bench_pending.keys())
        for ps_name, bname in sorted(already_done):
            bench_dir = output_dir / ps_name / bname
            if bench_dir.exists() and not (bench_dir / "results.csv").exists():
                logging.info(
                    f"Finalizing previously completed: {ps_name}/{bname}"
                )
                parse_and_compress_benchmark(
                    bench_dir, config_entries, not args.no_compress
                )

    # ── Dry-run summary ───────────────────────────────────────────────────────
    if args.dry_run:
        logging.info("=" * 60)
        logging.info(f"DRY RUN — {total} jobs would be launched")
        logging.info(
            f"  Parameter sets : {len(all_param_sets)}"
            f" × Benchmarks : {len(benchmark_sets)}"
        )
        avg_min = 20
        est_h = (total * avg_min) / 60 / args.max_workers
        logging.info(
            f"  Rough estimate : {total} × {avg_min} min / {args.max_workers} cores"
            f" ≈ {est_h:.1f} h  (assuming {avg_min} min avg per circuit)"
        )
        show = min(total, 15)
        for j in jobs[:show]:
            logging.info(f"  {j.param_set_name}/{j.benchmark_name}/{j.circuit_name}")
        if total > show:
            logging.info(f"  … and {total - show} more jobs.")
        logging.info("=" * 60)
        return 0

    # ── Execute ───────────────────────────────────────────────────────────────
    logging.info(
        f"Starting sweep: {total} jobs, max {args.max_workers} parallel workers"
    )
    csv_path = output_dir / "sweep_summary.csv"
    completed = failed = 0

    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit ALL jobs upfront.  The executor's internal queue + work-stealing
        # ensures a free worker always picks up the next waiting job immediately,
        # regardless of which parameter set it belongs to.
        future_to_job = {executor.submit(run_job, job): job for job in jobs}

        for future in as_completed(future_to_job):
            job = future_to_job[future]
            try:
                result = future.result()
            except Exception as exc:
                result = JobResult(
                    param_set_name=job.param_set_name,
                    benchmark_name=job.benchmark_name,
                    circuit_name=job.circuit_name,
                    success=False,
                    message=str(exc),
                )

            append_csv_row(csv_path, result)
            done = completed + failed + 1
            progress = f"[{done}/{total}]"

            if result.success:
                completed += 1
                metrics = (
                    f"CPD={result.cpd_ns}ns  WL={result.routed_wirelength}"
                    if result.cpd_ns is not None
                    else "(metrics not parsed)"
                )
                logging.info(
                    f"{progress} OK  "
                    f"{result.param_set_name}/{result.benchmark_name}/{result.circuit_name}"
                    f"  {result.runtime_seconds:.0f}s  {metrics}"
                )
            else:
                failed += 1
                logging.error(
                    f"{progress} FAIL "
                    f"{result.param_set_name}/{result.benchmark_name}/{result.circuit_name}"
                    f"  — {result.message}"
                )

            # Finalize a (param_set, benchmark) once all its circuits complete
            if config_entries:
                key = (result.param_set_name, result.benchmark_name)
                ps_bench_pending[key] -= 1
                if ps_bench_pending[key] == 0:
                    bench_dir = output_dir / result.param_set_name / result.benchmark_name
                    action = "compressing" if not args.no_compress else "skipping compress"
                    logging.info(
                        f"All circuits done for "
                        f"{result.param_set_name}/{result.benchmark_name} — "
                        f"parsing metrics and {action}"
                    )
                    parse_and_compress_benchmark(
                        bench_dir, config_entries, not args.no_compress
                    )

    logging.info(
        f"\n{'=' * 60}\n"
        f"SWEEP COMPLETE: {completed} passed, {failed} failed / {total} total\n"
        f"Summary CSV: {csv_path}\n"
        f"{'=' * 60}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
