"""The tpx3dump process flags the Advanced tab offers, and the argv they make.

One table drives the whole thing -- the widgets, the saved settings, the
amber summary on the Process tab, reset, and the command line -- so a flag is
added in one place. The notes and defaults are taken from
`tpx3dump process --help`; -i / -o are the queue's business and -h is not a
processing option, so those three are not listed.

Qt-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .backend import LOG_LEVELS
from .tdc import TOF_TDC_REFERENCES


@dataclass(frozen=True)
class Flag:
    flag: str           # as passed, e.g. "--eps-t"
    key: str            # settings key; a switch_choice also stores key + "_on"
    kind: str           # number | int | duration | path | choice | switch | switch_choice
    default: str        # tpx3dump's own default, as its --help prints it
    note: str           # one line shown beside the control
    tip: str = ""       # the longer story, as a tooltip
    choices: tuple = () # the values offered; the GUI adds a "default" entry


# Time values carry their unit: tpx3dump parses "100ns", "0.495s", ...
DURATION_UNITS = ("s", "ms", "us", "ns", "ps", "fs")
_DURATION = re.compile(r"^\d+(\.\d+)?(" + "|".join(DURATION_UNITS) + r")$")
_INT = re.compile(r"^\d+$")
_NUMBER = re.compile(r"^\d+(\.\d+)?$")

FLAG_GROUPS = [
    ("Detector and timing", [
        Flag("--layout", "layout", "choice", "single",
             "chip arrangement: single, quad (2x2) or octal (2x4)",
             "Must match the detector the data was taken with.",
             ("single", "quad", "octal")),
        Flag("--n-phases", "n_phases", "choice", "1",
             "PLL phase correction; 16 minimises the error, 1 = off",
             "Number of phases of the acquisition's phase-locked loop. It "
             "corrects a timing error in the design of the tpx3 chipboard; "
             "tpx3dump's help notes the correction is often applied and that "
             "16 minimises the error. 1 turns it off.",
             ("1", "2", "4", "8", "16")),
        Flag("--tof-tdc-reference", "tof_tdc_reference", "switch_choice", "",
             "TDC edge that starts the ToF clock; unticked = no ToF",
             "Fills PixelHits/tof with each hit's time since the chosen TDC "
             "edge. Left unticked, tpx3dump does not compute ToF at all.\n"
             "Independent of 'Add TDC columns' under After processing, "
             "which this GUI computes once tpx3dump is done.",
             tuple(TOF_TDC_REFERENCES)),
    ]),
    ("Clustering", [
        Flag("--eps-s", "eps_s", "number", "1",
             "largest gap between hits of one cluster, in pixels"),
        Flag("--eps-t", "eps_t", "duration", "100ns",
             "largest time gap between hits of one cluster, with a unit",
             "Write the unit with the number, e.g. 200ns or 1.5us. "
             "Valid units: " + ", ".join(DURATION_UNITS) + "."),
        Flag("--clustering-algorithm", "clustering_algorithm", "choice",
             "DFSCluster",
             "DFSCluster: stable, slower;  Kuttruff2024: faster, experimental",
             "Kuttruff2024: https://doi.org/10.1016/j.ultramic.2023.113864",
             ("DFSCluster", "Kuttruff2024")),
        Flag("--kuttruff-buffer-size", "kuttruff_buffer_size", "int", "10",
             "the B parameter of Kuttruff2024; ignored by DFSCluster"),
        Flag("--disable-clustering", "disable_clustering", "switch", "",
             "sort the hits but do not cluster them"),
        Flag("--raw-only", "raw_only", "switch", "",
             "unpack the hits only: no sorting, no clustering",
             "The TDC columns and the cluster plots need the sorted, "
             "clustered output, so they will not work on such a file."),
    ]),
    ("Output file", [
        Flag("--discard-pixel-data", "discard_pixel_data", "switch", "",
             "leave PixelHits out -- usually most of the file",
             "The file then holds the clusters only. The pixel hitmap and "
             "PixelHits TDC columns need PixelHits."),
        Flag("--compression-algorithm", "compression_algorithm", "choice",
             "None", "compress the datasets; the default is uncompressed",
             "Deflate is gzip and opens anywhere. The Blosc variants are "
             "faster, but h5py reads them only with the hdf5plugin package "
             "installed -- without it the Inspect tab cannot open the data.",
             ("Deflate", "BloscLz4", "BloscLz4hc", "BloscBlosclz",
              "BloscSnappy", "BloscZlib", "BloscZstd")),
        Flag("--compression-level", "compression_level", "choice", "5",
             "1 = fastest, 9 = smallest, off = none",
             choices=("off", "1", "2", "3", "4", "5", "6", "7", "8", "9")),
        Flag("--compression-shuffle", "compression_shuffle", "choice", "Byte",
             "byte or bit shuffle before compressing",
             choices=("None", "Bit", "Byte")),
        Flag("--compression-nthreads", "compression_nthreads", "int",
             "all cores", "compression threads; Blosc only"),
        Flag("--hdf5-chunk-size", "hdf5_chunk_size", "int", "15000",
             "HDF5 chunk size; the help says bytes, files show rows",
             "tpx3dump's help gives the unit as bytes, but its output files "
             "have chunks of 15000 rows at the default."),
    ]),
    ("Timewalk", [
        Flag("--calculate-timewalk-statistics", "calculate_timewalk_statistics",
             "switch", "", "accumulate timewalk statistics into the output"),
        Flag("--timewalk-file", "timewalk_file", "path", "",
             "earlier output to start the statistics from; needs the box above",
             "An .hdf5 from a previous tpx3dump run with a timewalk correction "
             "matrix. Statistics accumulate on top of it across similar "
             "experiments. If the file cannot be read, tpx3dump starts afresh."),
        Flag("--ctot-cut", "ctot_cut", "int", "450",
             "cluster ToT (its largest ToT) used to build the timewalk LUT"),
    ]),
    ("Performance and logging", [
        Flag("--time-bin-interval", "time_bin_interval", "duration", "500ms",
             "data per processing segment, with a unit; speed and memory only",
             "Too small makes processing inefficient. Too large for memory "
             "triggers tpx3dump's back-off, which avoids a crash but runs "
             "slower. Does not change the output."),
        Flag("--num-time-bins", "num_time_bins", "int", "3",
             "segments cached before processing; 3 x 500ms = 1.5 s"),
        Flag("--log-level", "log_level", "choice", "info",
             "how much tpx3dump writes to the log",
             choices=tuple(lv for lv in LOG_LEVELS if lv)),
    ]),
]

FLAGS = [f for _title, group in FLAG_GROUPS for f in group]


def flag_bits(values: dict, translate=str) -> list[list[str]]:
    """The argv pieces, one list per flag that is set.

    `values` maps each Flag.key to the control's text (or bool for a switch);
    missing keys count as unset. `translate` maps a path-valued flag onto the
    machine tpx3dump runs on, e.g. Backend.translate.
    """
    out = []
    for f in FLAGS:
        if f.kind == "switch":
            if values.get(f.key):
                out.append([f.flag])
        elif f.kind == "switch_choice":
            if values.get(f.key + "_on") and values.get(f.key):
                out.append([f.flag, values[f.key]])
        else:
            val = str(values.get(f.key, "")).strip()
            if not val:
                continue
            if f.kind == "duration":
                val = val.replace(" ", "")
            elif f.kind == "path":
                val = translate(val)
            out.append([f.flag, val])
    return out


def flag_args(values: dict, translate=str) -> list[str]:
    return [a for bit in flag_bits(values, translate) for a in bit]


def flag_problems(values: dict) -> list[str]:
    """Values tpx3dump would reject, worded for a message box."""
    problems = []
    for f in FLAGS:
        if f.kind not in ("number", "int", "duration"):
            continue
        val = str(values.get(f.key, "")).strip()
        if not val:
            continue
        if f.kind == "duration" and not _DURATION.match(val.replace(" ", "")):
            problems.append(f"{f.flag} needs a number with a unit, e.g. "
                            f"{f.default} -- got '{val}'.")
        elif f.kind == "int" and not _INT.match(val):
            problems.append(f"{f.flag} needs a whole number -- got '{val}'.")
        elif f.kind == "number" and not _NUMBER.match(val):
            problems.append(f"{f.flag} needs a number -- got '{val}'.")
    return problems
