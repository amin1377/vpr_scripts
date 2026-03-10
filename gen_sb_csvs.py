#!/usr/bin/env python3
"""
Generate CRR switch-block CSV templates with random connectivity for:
  main, io, mult_36_0..3, memory_0..5

Only L4 (length-4) segments are used.
Channel width W is taken as a command-line parameter.

Pin PTCs are from the rr_graph block_type/pin_class section:
  - clb     (height=1) : I[0:39]=ptc 0-39, O[0:19]=41-60  (cin/cout/clk excluded)
  - io      (height=1) : io[k].outpad=3k, io[k].inpad=3k+1  (k=0..7; clock excluded)
  - mult_36 (height=4) : a[0:35]=ptc 0-35, b[0:35]=36-71, out[0:71]=72-143
  - memory  (height=6) : addr1[0:14]=0-14, addr2[0:14]=15-29, data[0:63]=30-93,
                         we1=94, we2=95, out[0:63]=96-159  (clk excluded)

Pinlocations (arch file), by tile row (yoffset):
  mult_36:
    yoffset=0 RIGHT : a[22:18], b[22:18],               out[44:36]
    yoffset=1 RIGHT : a[27:23], b[27:23],               out[53:45]
    yoffset=2 RIGHT : a[32:28], b[32:28],               out[62:54]
    yoffset=3 RIGHT : a[35:33], b[35:33],               out[71:63]
    yoffset=3 TOP   : a[17:0],  b[17:0],                out[35:0]
  memory:
    yoffset=0 RIGHT : addr1[14:0],                      out[8:0]
    yoffset=1 RIGHT : addr2[14:0],                      out[17:9]
    yoffset=2 RIGHT : data[15:0],                       out[26:18]
    yoffset=3 RIGHT : data[31:16],                      out[35:27]
    yoffset=4 RIGHT : data[47:32],                      out[44:36]
    yoffset=5 RIGHT : data[63:48],                      out[53:45]
    yoffset=5 TOP   : we1(94), we2(95),                 out[63:54]
"""

import argparse
import csv
import os
import random

L = 4  # segment length (only L4 used)

# ---------------------------------------------------------------------------
# Helper: wire sink/source structures
# ---------------------------------------------------------------------------

def lanes_per_side(W):
    return W // (2 * L)

def make_wire_sink_cols(W):
    """4 directions × lanes_per_side lanes → list of (direction, lane)."""
    cols = []
    for direction in ['Left', 'Right', 'Top', 'Bottom']:
        for lane in range(1, lanes_per_side(W) + 1):
            cols.append((direction, lane))
    return cols

def make_wire_source_rows(W):
    """4 directions × lanes_per_side lanes × L taps → list of (direction, lane, tap)."""
    rows = []
    for direction in ['Left', 'Right', 'Top', 'Bottom']:
        for lane in range(1, lanes_per_side(W) + 1):
            for tap in range(1, L + 1):
                rows.append((direction, lane, tap))
    return rows

# ---------------------------------------------------------------------------
# Connectivity assignment helpers
# ---------------------------------------------------------------------------

def _greedy_assign(n_sinks, n_sources, fan_in, eligible_fn, rng):
    """
    Generic balanced greedy assignment: for each sink pick `fan_in` sources
    from eligible_fn(sink_idx), balancing source fanout.

    Returns:
        sink_to_sources : list[list[int]]  (indices into sources)
        src_fanout      : list[int]
    """
    src_fanout = [0] * n_sources
    sink_to_sources = [[] for _ in range(n_sinks)]

    sink_order = list(range(n_sinks))
    rng.shuffle(sink_order)

    for j in sink_order:
        eligible = eligible_fn(j)
        if len(eligible) < fan_in:
            raise ValueError(
                f'Only {len(eligible)} eligible sources for sink {j}, need fan_in={fan_in}')
        # Sort by current fanout; random tiebreak to avoid bias
        eligible.sort(key=lambda i: (src_fanout[i], rng.random()))
        chosen = eligible[:fan_in]
        sink_to_sources[j] = chosen
        for i in chosen:
            src_fanout[i] += 1

    return sink_to_sources, src_fanout


def assign_wire_wire(wire_sinks, wire_sources, fan_in, rng):
    """
    Wire-to-wire connections, no U-turn (sink_dir ≠ src_dir).
    Returns sink_to_sources and src_fanout.
    """
    n_sink = len(wire_sinks)
    n_src  = len(wire_sources)

    def eligible_fn(j):
        sink_dir = wire_sinks[j][0]
        return [i for i in range(n_src) if wire_sources[i][0] != sink_dir]

    return _greedy_assign(n_sink, n_src, fan_in, eligible_fn, rng)


def assign_wire_ipin(n_wire_src, n_ipin, fan_in, rng):
    """
    Wire-to-IPIN connections.  Each IPIN sink gets `fan_in` wire-source
    connections.  After the greedy pass every wire source with zero IPIN
    connections is forced to connect to a random IPIN.

    Returns:
        ipin_to_sources : list[list[int]]   (indices into wire_sources)
        src_ipin_fanout : list[int]
    """
    src_fanout = [0] * n_wire_src
    ipin_to_sources = [[] for _ in range(n_ipin)]

    ipin_order = list(range(n_ipin))
    rng.shuffle(ipin_order)

    for k in ipin_order:
        eligible = list(range(n_wire_src))
        eligible.sort(key=lambda i: (src_fanout[i], rng.random()))
        if len(eligible) < fan_in:
            raise ValueError(
                f'Only {len(eligible)} wire sources, need fan_in_ipin={fan_in}')
        chosen = eligible[:fan_in]
        ipin_to_sources[k] = chosen
        for i in chosen:
            src_fanout[i] += 1

    # Force every wire source to connect to at least one IPIN
    if n_ipin > 0:
        for i in range(n_wire_src):
            if src_fanout[i] == 0:
                k = rng.randrange(n_ipin)
                if i not in ipin_to_sources[k]:
                    ipin_to_sources[k].append(i)
                    src_fanout[i] += 1

    return ipin_to_sources, src_fanout


def assign_opin_wire(n_opin, n_wire_sink, fan_out, rng):
    """
    OPIN-to-wire connections (no IPIN sinks).  Each OPIN connects to
    `fan_out` wire sink columns, spread evenly.

    Returns:
        opin_to_sinks       : list[list[int]]  (indices into wire_sinks)
        wire_fanin_from_opin: list[int]
    """
    wire_fanin = [0] * n_wire_sink
    opin_to_sinks = []

    for _ in range(n_opin):
        sinks_sorted = sorted(range(n_wire_sink),
                              key=lambda j: (wire_fanin[j], rng.random()))
        if n_wire_sink < fan_out:
            raise ValueError(
                f'Only {n_wire_sink} wire sinks, need fan_out_opin={fan_out}')
        chosen = sinks_sorted[:fan_out]
        opin_to_sinks.append(chosen)
        for j in chosen:
            wire_fanin[j] += 1

    return opin_to_sinks, wire_fanin

# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def build_csv(filepath, W, ipin_cols, opin_rows,
              fan_in_wire, fan_in_ipin, fan_out_opin, seed=42):
    """
    Write a CRR switch-block CSV with random balanced connectivity.

    Sink columns  : wire columns (Left/Right/Top/Bottom × lanes_per_side)
                    followed by IPIN columns.
    Source rows   : wire rows first, then OPIN rows.

    Connectivity rules
    ------------------
    Wire sinks   : fan_in_wire sources from wire rows, no U-turn.
    IPIN sinks   : fan_in_ipin sources from wire rows only; every wire
                   source row is guaranteed ≥1 IPIN connection.
    OPIN sources : fan_out_opin wire sink connections, NO IPIN connections;
                   spread evenly across wire sinks.
    """
    seg = 'L4'
    wire_sinks   = make_wire_sink_cols(W)
    wire_sources = make_wire_source_rows(W)

    n_wire_sink = len(wire_sinks)
    n_ipin      = len(ipin_cols)
    n_sink      = n_wire_sink + n_ipin

    n_wire_src  = len(wire_sources)
    n_opin      = len(opin_rows)
    n_src       = n_wire_src + n_opin

    rng = random.Random(seed)

    # Connection matrix: conn[src_idx][sink_idx] = 1 or ''
    conn = [['' for _ in range(n_sink)] for _ in range(n_src)]

    def rand_delay():
        return rng.randint(50, 70)

    # ---- 1. Wire-to-wire (no U-turn) ----------------------------------------
    ww_sink_to_src, wire_fanout = assign_wire_wire(
        wire_sinks, wire_sources, fan_in_wire, rng)
    for j, srcs in enumerate(ww_sink_to_src):
        for i in srcs:
            conn[i][j] = rand_delay()

    # ---- 2. Wire-to-IPIN ----------------------------------------------------
    wi_ipin_to_src, wire_ipin_fanout = assign_wire_ipin(
        n_wire_src, n_ipin, fan_in_ipin, rng)
    for k, srcs in enumerate(wi_ipin_to_src):
        j = n_wire_sink + k
        for i in srcs:
            conn[i][j] = rand_delay()

    # ---- 3. OPIN-to-wire (no IPIN) ------------------------------------------
    ow_opin_to_sink, _ = assign_opin_wire(
        n_opin, n_wire_sink, fan_out_opin, rng)
    for k, sinks in enumerate(ow_opin_to_sink):
        src_idx = n_wire_src + k
        for j in sinks:
            conn[src_idx][j] = rand_delay()

    # ---- Compute actual fan-in per sink (for header row 2) ------------------
    sink_fanin = [sum(1 for i in range(n_src) if conn[i][j] != '')
                  for j in range(n_sink)]

    # ---- Build CSV ----------------------------------------------------------
    all_rows = []

    r0 = ['', '', '', ''] + [d for (d, _) in wire_sinks] + ['IPIN'] * n_ipin
    all_rows.append(r0)

    r1 = ['', '', '', ''] + [seg] * n_wire_sink + [seg] * n_ipin
    all_rows.append(r1)

    r2 = ['', '', '', ''] + sink_fanin
    all_rows.append(r2)

    r3 = ['', '', '', ''] + [lane for (_, lane) in wire_sinks] + \
         [ptc for (ptc, _) in ipin_cols]
    all_rows.append(r3)

    r4 = ['', '', '', ''] + [''] * n_wire_sink + \
         [name for (_, name) in ipin_cols]
    all_rows.append(r4)

    for i, (direction, lane, tap) in enumerate(wire_sources):
        all_rows.append([direction, seg, f'{lane}.0', tap] + conn[i])

    for k, (ptc, name) in enumerate(opin_rows):
        all_rows.append(['OPIN', seg, f'{ptc}.0', name] + conn[n_wire_src + k])

    with open(filepath, 'w', newline='') as f:
        csv.writer(f).writerows(all_rows)

    return wire_fanout, wire_ipin_fanout

# ---------------------------------------------------------------------------
# Pin definitions per template
# ---------------------------------------------------------------------------

def clb_pins():
    """
    CLB pins (from arch: input I[40], output O[20]).
    IPIN cols : I[0:39] (ptc 0-39)
    OPIN rows : O[0:19] (ptc 41-60)
    cin, cout, clk excluded.
    """
    ipin_cols = [(i, f'clb.I[{i}]') for i in range(40)]
    opin_rows  = [(41 + i, f'clb.O[{i}]') for i in range(20)]
    return ipin_cols, opin_rows


def io_pins():
    """
    IO tile: 8 sub-tiles (from arch: input outpad[1], output inpad[1]).
    IPIN cols : outpad (ptc 3k) for k=0..7
    OPIN rows : inpad  (ptc 3k+1) for k=0..7
    clock excluded.
    """
    ipin_cols = [(3 * k,      f'io[{k}].outpad[0]') for k in range(8)]
    opin_rows  = [(3 * k + 1, f'io[{k}].inpad[0]')  for k in range(8)]
    return ipin_cols, opin_rows


def mult36_pins(row):
    """
    mult_36 pins for switch-box row `row` (0=bottom … 3=top).

    Pinlocations (arch):
      row 0 RIGHT : a[22:18]  ptc 18-22  | b[22:18]  ptc 54-58  | out[44:36] ptc 108-116
      row 1 RIGHT : a[27:23]  ptc 23-27  | b[27:23]  ptc 59-63  | out[53:45] ptc 117-125
      row 2 RIGHT : a[32:28]  ptc 28-32  | b[32:28]  ptc 64-68  | out[62:54] ptc 126-134
      row 3 RIGHT : a[35:33]  ptc 33-35  | b[35:33]  ptc 69-71  | out[71:63] ptc 135-143
      row 3 TOP   : a[17:0]   ptc  0-17  | b[17:0]   ptc 36-53  | out[35:0]  ptc  72-107
    """
    ipin_cols = []
    opin_rows = []

    if row == 0:
        ipin_cols  = [(p,      f'mult_36.a[{p}]') for p in range(18, 23)]
        ipin_cols += [(p + 36, f'mult_36.b[{p}]') for p in range(18, 23)]
        opin_rows  = [(72 + 36 + i, f'mult_36.out[{36 + i}]') for i in range(9)]

    elif row == 1:
        ipin_cols  = [(p,      f'mult_36.a[{p}]') for p in range(23, 28)]
        ipin_cols += [(p + 36, f'mult_36.b[{p}]') for p in range(23, 28)]
        opin_rows  = [(72 + 45 + i, f'mult_36.out[{45 + i}]') for i in range(9)]

    elif row == 2:
        ipin_cols  = [(p,      f'mult_36.a[{p}]') for p in range(28, 33)]
        ipin_cols += [(p + 36, f'mult_36.b[{p}]') for p in range(28, 33)]
        opin_rows  = [(72 + 54 + i, f'mult_36.out[{54 + i}]') for i in range(9)]

    elif row == 3:
        # IPIN TOP: a[0:17], b[0:17]
        ipin_cols  = [(p,      f'mult_36.a[{p}]') for p in range(18)]
        ipin_cols += [(p + 36, f'mult_36.b[{p}]') for p in range(18)]
        # IPIN RIGHT: a[33:35], b[33:35]
        ipin_cols += [(p,      f'mult_36.a[{p}]') for p in range(33, 36)]
        ipin_cols += [(p + 36, f'mult_36.b[{p}]') for p in range(33, 36)]
        # OPIN RIGHT: out[63:71] ptc 135-143
        opin_rows  = [(72 + 63 + i, f'mult_36.out[{63 + i}]') for i in range(9)]
        # OPIN TOP: out[0:35] ptc 72-107
        opin_rows += [(72 + i, f'mult_36.out[{i}]') for i in range(36)]

    else:
        raise ValueError(f'mult_36 has rows 0-3, got {row}')

    ipin_cols.sort(key=lambda x: x[0])
    opin_rows.sort(key=lambda x: x[0])
    return ipin_cols, opin_rows


def memory_pins(row):
    """
    memory pins for switch-box row `row` (0=bottom … 5=top).

    Pinlocations (arch):
      row 0 RIGHT : addr1[14:0]  ptc  0-14  | out[8:0]    ptc  96-104
      row 1 RIGHT : addr2[14:0]  ptc 15-29  | out[17:9]   ptc 105-113
      row 2 RIGHT : data[15:0]   ptc 30-45  | out[26:18]  ptc 114-122
      row 3 RIGHT : data[31:16]  ptc 46-61  | out[35:27]  ptc 123-131
      row 4 RIGHT : data[47:32]  ptc 62-77  | out[44:36]  ptc 132-140
      row 5 RIGHT : data[63:48]  ptc 78-93  | out[53:45]  ptc 141-149
      row 5 TOP   : we1(94) we2(95)         | out[63:54]  ptc 150-159
    """
    ipin_cols = []
    opin_rows = []

    if row == 0:
        ipin_cols = [(p, f'memory.addr1[{p}]')      for p in range(15)]
        opin_rows = [(96 + i, f'memory.out[{i}]')   for i in range(9)]

    elif row == 1:
        ipin_cols = [(p, f'memory.addr2[{p - 15}]') for p in range(15, 30)]
        opin_rows = [(105 + i, f'memory.out[{9 + i}]') for i in range(9)]

    elif row == 2:
        ipin_cols = [(p, f'memory.data[{p - 30}]')  for p in range(30, 46)]
        opin_rows = [(114 + i, f'memory.out[{18 + i}]') for i in range(9)]

    elif row == 3:
        ipin_cols = [(p, f'memory.data[{p - 30}]')  for p in range(46, 62)]
        opin_rows = [(123 + i, f'memory.out[{27 + i}]') for i in range(9)]

    elif row == 4:
        ipin_cols = [(p, f'memory.data[{p - 30}]')  for p in range(62, 78)]
        opin_rows = [(132 + i, f'memory.out[{36 + i}]') for i in range(9)]

    elif row == 5:
        # IPIN RIGHT: data[48:63]
        ipin_cols  = [(p, f'memory.data[{p - 30}]') for p in range(78, 94)]
        # IPIN TOP: we1, we2 (clk excluded)
        ipin_cols += [(94, 'memory.we1[0]')]
        ipin_cols += [(95, 'memory.we2[0]')]
        # OPIN RIGHT: out[45:53] ptc 141-149
        opin_rows  = [(141 + i, f'memory.out[{45 + i}]') for i in range(9)]
        # OPIN TOP: out[54:63] ptc 150-159
        opin_rows += [(150 + i, f'memory.out[{54 + i}]') for i in range(10)]

    else:
        raise ValueError(f'memory has rows 0-5, got {row}')

    ipin_cols.sort(key=lambda x: x[0])
    opin_rows.sort(key=lambda x: x[0])
    return ipin_cols, opin_rows

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate CRR switch-block CSV templates with random connectivity.')
    parser.add_argument('--W', type=int, required=True,
                        help='Channel width (must be a multiple of 8 for L4 segments)')
    parser.add_argument('--fan_in_wire', type=int, required=True,
                        help='Fan-in for each wire sink from wire sources (no U-turn)')
    parser.add_argument('--fan_in_ipin', type=int, required=True,
                        help='Fan-in for each IPIN sink from wire sources')
    parser.add_argument('--fan_out_opin', type=int, required=True,
                        help='Fan-out for each OPIN source to wire sinks')
    parser.add_argument('--out_dir', default='.',
                        help='Output directory for generated CSV files')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for reproducibility (default: 42)')
    args = parser.parse_args()

    W = args.W
    if W % (2 * L) != 0:
        parser.error(f'W must be a multiple of {2*L} (got {W})')

    fan_in_wire  = args.fan_in_wire
    fan_in_ipin  = args.fan_in_ipin
    fan_out_opin = args.fan_out_opin

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    templates = {
        'main':      clb_pins(),
        'io':        io_pins(),
        'mult_36_0': mult36_pins(0),
        'mult_36_1': mult36_pins(1),
        'mult_36_2': mult36_pins(2),
        'mult_36_3': mult36_pins(3),
        'memory_0':  memory_pins(0),
        'memory_1':  memory_pins(1),
        'memory_2':  memory_pins(2),
        'memory_3':  memory_pins(3),
        'memory_4':  memory_pins(4),
        'memory_5':  memory_pins(5),
    }

    lanes    = lanes_per_side(W)
    n_wire_src = 4 * lanes * L
    n_wire_snk = 4 * lanes
    ideal_wire_fanout = fan_in_wire * n_wire_snk / n_wire_src  # expected per source
    print(f'W={W}, L={L}: {lanes} lanes/side, '
          f'{n_wire_src} wire source rows, {n_wire_snk} wire sink cols')
    print(f'fan_in_wire={fan_in_wire}  fan_in_ipin={fan_in_ipin}  '
          f'fan_out_opin={fan_out_opin}  seed={args.seed}')
    print(f'Ideal wire source fanout = {ideal_wire_fanout:.2f}')
    print()

    for name, (ipin_cols, opin_rows) in templates.items():
        fname = os.path.join(out_dir, f'sb_{name}.csv')
        wire_fanout, wire_ipin_fanout = build_csv(
            fname, W, ipin_cols, opin_rows,
            fan_in_wire, fan_in_ipin, fan_out_opin, seed=args.seed)

        fo_min, fo_max = min(wire_fanout), max(wire_fanout)
        print(f'  sb_{name}.csv')
        print(f'    wire source rows : {n_wire_src}  '
              f'fanout range [{fo_min}, {fo_max}]')
        if ipin_cols:
            fi_min, fi_max = min(wire_ipin_fanout), max(wire_ipin_fanout)
            print(f'    IPIN sink cols   : {len(ipin_cols)}  '
                  f'wire-src→IPIN connections per row [{fi_min}, {fi_max}]')
        else:
            print(f'    IPIN sink cols   : 0')
        print(f'    OPIN source rows : {len(opin_rows)}  '
              f'fan-out={fan_out_opin} each (wire sinks only)')
        print()


if __name__ == '__main__':
    main()
