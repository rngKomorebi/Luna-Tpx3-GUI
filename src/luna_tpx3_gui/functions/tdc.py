"""TDC post-processing: read /TDCEvents, tag hits and clusters with the edge
they follow, and write those columns back into the .hdf5.

Qt-free. h5py, numpy and pandas are imported inside the functions that need
them, so importing this module needs none of them.
"""

from __future__ import annotations

# tpx3dump's --tof-tdc-reference: which TDC edge starts the time-of-flight
# clock. Left off, tpx3dump uses its own default reference.
TOF_TDC_REFERENCES = ["TDC1Rising", "TDC1Falling",
                      "TDC2Rising", "TDC2Falling"]

# --- TDC ------------------------------------------------------------------
# tpx3dump writes every TDC edge it saw into /TDCEvents as
# (tdc_type u1, trigger_count u2, timestamp u8). The type codes are the same
# four references --tof-tdc-reference accepts, numbered from one.
TDC_DATASET = "TDCEvents"
TDC_TYPES = {1: "TDC1Rising", 2: "TDC1Falling",
             3: "TDC2Rising", 4: "TDC2Falling"}
TDC_TYPE_CODES = {name: code for code, name in TDC_TYPES.items()}

# Every timestamp in the file -- TDCEvents/timestamp, PixelHits/toa and
# Clusters/ctoa alike -- counts 100 fs ticks off one clock, which is what makes
# the hit-to-edge subtraction below meaningful.
TDC_SECONDS_PER_TICK = 1e-13

# "tag every row with the last reference edge before it", per source dataset:
# which dataset holds the row times, which field they live in, and where the
# TDC columns for it are written. The tagged dataset is row-aligned 1:1 with
# its source, so a reader concatenates the two into one frame.
TDC_SOURCES = {"PixelHits": ("toa", "PixelHitsTDC"),
               "Clusters": ("ctoa", "ClustersTDC")}

# The columns themselves. Packed, not aligned: these compress to almost
# nothing (tdc and tdc_trigger are constant across a whole trigger's worth of
# rows) and the width still matters for a hundred-million-hit file.
TDC_COLUMN_FIELDS = [
    ("tdc", "<u8"),          # timestamp of the reference edge, 100 fs ticks
    ("tdc_dt", "<i8"),       # row time minus that edge, same ticks
    ("tdc_index", "<i4"),    # row in the deduped TDC table, -1 = none
    ("tdc_trigger", "<u2"),  # tpx3dump's trigger_count for that edge
    ("tdc_type", "u1"),      # 1..4 per TDC_TYPES, 0 = no edge yet
]
TDC_COLUMN_NAMES = [name for name, _ in TDC_COLUMN_FIELDS]

# Rows that precede the first reference edge have no edge to measure from.
# tpx3dump signals the same thing in PixelHits/tof with -1, so match it rather
# than invent a second convention.
TDC_UNSET = -1

# Marks a dataset this GUI wrote, so re-tagging a file replaces its own
# previous columns and refuses to touch anything else.
TDC_STAMP = "luna_tpx3_gui.tdc_columns"

# "Any edge" tags each row from the most recent edge of whatever type, instead
# of following one reference. Useful when TDC1 and TDC2 both carry triggers.
TDC_REFERENCE_ANY = "Any edge"
TDC_REFERENCES = TOF_TDC_REFERENCES + [TDC_REFERENCE_ANY]

# Rows read per slice when tagging. 2e6 hits is ~32 MB of toa, so a file far
# larger than memory still tags in bounded space.
TDC_CHUNK = 2_000_000

# ---------------------------------------------------------------------------
# TDC: read /TDCEvents, and tag hits and clusters with the edge they follow
#
# Nothing below touches Qt, so the same functions work from a notebook:
#
#     import luna_tpx3_gui as g
#     df = g.read_tdcs("run.hdf5")                 # the edges themselves
#     g.add_tdc_columns("run.hdf5", "TDC1Rising")  # write the columns
#     df = g.read_with_tdc("run.hdf5", "Clusters") # frame with a tdc column
# ---------------------------------------------------------------------------

def read_tdc_events(f, np):
    """Physical TDC edges from an open HDF5 file, sorted by timestamp.

    Every chip in the layout repeats the TDC packet, so a quad carries each
    edge four times and an octal eight. Deduplicating on (tdc_type, timestamp)
    collapses those back to the edges that actually happened -- the same thing
    ASI's read_tdcs.py does, and the reason a 40-row /TDCEvents in a quad file
    describes only ten triggers.
    """
    if TDC_DATASET not in f:
        return None
    raw = f[TDC_DATASET][:]
    if raw.shape[0] == 0:
        return raw
    # Sort by timestamp with tdc_type as the tiebreak, which puts every repeat
    # of one edge next to its twin so a neighbour test is enough to drop them.
    ev = raw[np.lexsort((raw["tdc_type"], raw["timestamp"]))]
    keep = np.ones(len(ev), dtype=bool)
    keep[1:] = ((ev["timestamp"][1:] != ev["timestamp"][:-1]) |
                (ev["tdc_type"][1:] != ev["tdc_type"][:-1]))
    return ev[keep]


def tdc_reference_edges(events, reference, np):
    """The edges that act as the clock: one type, or all of them."""
    if events is None or len(events) == 0:
        return events
    if reference in (None, "", TDC_REFERENCE_ANY):
        return events
    code = TDC_TYPE_CODES.get(reference)
    if code is None:
        raise ValueError("Unknown TDC reference: " + str(reference))
    return events[events["tdc_type"] == code]


def describe_tdc_types(events, np):
    """'20 TDC1Rising, 20 TDC1Falling' -- for error messages and the summary."""
    if events is None or len(events) == 0:
        return "no edges"
    codes, counts = np.unique(events["tdc_type"], return_counts=True)
    return ", ".join("%s %s" % (format(int(c), ","),
                                TDC_TYPES.get(int(t), "type %d" % int(t)))
                     for t, c in zip(codes, counts))


def tag_times_with_tdc(times, edges, np):
    """TDC columns for one block of row times.

    Each row is attributed to the last reference edge at or before it -- the
    trigger it belongs to. Rows arriving before the first edge get TDC_UNSET,
    matching how tpx3dump leaves PixelHits/tof at -1 when it has no reference
    to measure from.
    """
    out = np.zeros(len(times), dtype=np.dtype(TDC_COLUMN_FIELDS))
    out["tdc_index"] = TDC_UNSET
    out["tdc_dt"] = TDC_UNSET
    if len(times) == 0 or edges is None or len(edges) == 0:
        return out
    stamps = edges["timestamp"]
    # side="right" so a hit landing exactly on an edge belongs to that edge
    # rather than to the one before it.
    idx = np.searchsorted(stamps, times, side="right") - 1
    has = idx >= 0
    if not has.any():
        return out
    sel = idx[has]
    out["tdc_index"][has] = sel
    out["tdc"][has] = stamps[sel]
    out["tdc_type"][has] = edges["tdc_type"][sel]
    out["tdc_trigger"][has] = edges["trigger_count"][sel]
    # int64 on purpose: times is unsigned, so an unsigned difference would wrap
    # to something enormous instead of going negative.
    out["tdc_dt"][has] = (times[has].astype("int64") -
                          stamps[sel].astype("int64"))
    return out


def add_tdc_columns(path, reference="TDC1Rising", log=None):
    """Write row-aligned TDC columns into an existing tpx3dump HDF5.

    Adds /PixelHitsTDC and /ClustersTDC beside the datasets they describe, each
    row i carrying the trigger that row i of the source belongs to. The
    originals are never rewritten: an HDF5 compound dataset has a fixed dtype,
    so a genuine extra field would mean recreating the whole thing, and these
    files are the only copy of the measurement. Readers join the two, which
    read_with_tdc() below does.

    Returns {dataset name: summary dict}, and raises on anything wrong.
    """
    import h5py
    import numpy as np

    say = log if log is not None else (lambda _m: None)
    result = {}
    with h5py.File(path, "r+") as f:
        events = read_tdc_events(f, np)
        if events is None:
            raise ValueError(
                "No /%s in this file. It came from a tpx3dump older than the "
                "TDC support, or the acquisition recorded no TDC at all."
                % TDC_DATASET)
        if len(events) == 0:
            raise ValueError("/%s is empty: this run saw no TDC edges, so there "
                             "is nothing to tag rows with." % TDC_DATASET)
        edges = tdc_reference_edges(events, reference, np)
        if len(edges) == 0:
            raise ValueError("No %s edges in this file. It has %s."
                             % (reference, describe_tdc_types(events, np)))
        say("  %d TDC edge(s) after dedup, %d of them %s"
            % (len(events), len(edges), reference))

        for src_name, (time_field, out_name) in TDC_SOURCES.items():
            if src_name not in f:
                continue
            src = f[src_name]
            n = src.shape[0]
            if n == 0:
                continue
            if out_name in f:
                # Only ever replace columns this GUI wrote. Anything else
                # under that name belongs to the user or to another tool.
                if f[out_name].attrs.get("written_by") != TDC_STAMP:
                    raise ValueError(
                        "/%s already exists and was not written by this GUI. "
                        "Refusing to replace it." % out_name)
                del f[out_name]
            dset = f.create_dataset(
                out_name, shape=(n,), dtype=np.dtype(TDC_COLUMN_FIELDS),
                # One chunk per tagging slice would be far too big to cache;
                # 64k rows is ~1.4 MB, which gzip likes and readers can stream.
                chunks=(min(n, 65536),), compression="gzip", compression_opts=4)
            tagged = 0
            for i in range(0, n, TDC_CHUNK):
                j = min(i + TDC_CHUNK, n)
                cols = tag_times_with_tdc(src[i:j][time_field], edges, np)
                dset[i:j] = cols
                tagged += int((cols["tdc_index"] >= 0).sum())
            dset.attrs["written_by"] = TDC_STAMP
            dset.attrs["source_dataset"] = src_name
            dset.attrs["source_time_field"] = time_field
            dset.attrs["tdc_reference"] = reference
            dset.attrs["seconds_per_tick"] = TDC_SECONDS_PER_TICK
            dset.attrs["n_reference_edges"] = len(edges)
            result[out_name] = {"rows": n, "tagged": tagged,
                                "source": src_name, "reference": reference}
            say("  /%s: %s of %s row(s) fall after a %s edge"
                % (out_name, format(tagged, ","), format(n, ","), reference))
    if not result:
        raise ValueError("This file has neither PixelHits nor Clusters to tag "
                         "(processed with --raw-only?).")
    return result


def read_tdcs(path):
    """The deduplicated TDC edges as a DataFrame, with decoded type and seconds.

    The direct equivalent of ASI's read_tdcs.py.
    """
    import h5py
    import numpy as np
    import pandas as pd

    with h5py.File(path, "r") as f:
        events = read_tdc_events(f, np)
    if events is None:
        raise ValueError("No /%s in %s" % (TDC_DATASET, path))
    df = pd.DataFrame(events)
    df["tdc_type"] = df["tdc_type"].map(TDC_TYPES)
    df["time_s"] = df["timestamp"] * TDC_SECONDS_PER_TICK
    return df


def read_with_tdc(path, which="Clusters", limit=None, reference=None):
    """One DataFrame of `which` with the TDC columns joined onto it.

    Uses the stored /...TDC dataset when add_tdc_columns() has written one;
    otherwise tags on the fly from /TDCEvents, so this also works on a file
    straight out of tpx3dump. Passing `reference` forces the on-the-fly path,
    which is how you look at a different edge without rewriting the file.
    `tdc_type` comes back as the readable name and `tdc_dt_s` as seconds, both
    derived here rather than stored.
    """
    import h5py
    import numpy as np
    import pandas as pd

    if which not in TDC_SOURCES:
        raise ValueError("Expected one of %s, got %r"
                         % (", ".join(TDC_SOURCES), which))
    time_field, out_name = TDC_SOURCES[which]
    with h5py.File(path, "r") as f:
        if which not in f or f[which].shape[0] == 0:
            raise ValueError("This file has no /%s rows." % which)
        total = f[which].shape[0]
        n = total if limit is None else min(int(limit), total)
        df = pd.DataFrame(f[which][:n])
        stored = out_name in f and reference is None
        if stored:
            cols = f[out_name][:n]
            used = f[out_name].attrs.get("tdc_reference", "")
        else:
            events = read_tdc_events(f, np)
            if events is None or len(events) == 0:
                raise ValueError("No usable /%s in this file." % TDC_DATASET)
            used = reference or TDC_REFERENCE_ANY
            cols = tag_times_with_tdc(f[which][:n][time_field],
                                      tdc_reference_edges(events, used, np), np)
    for name in TDC_COLUMN_NAMES:
        df[name] = cols[name]
    df["tdc_type"] = df["tdc_type"].map(TDC_TYPES)
    # Keep the sentinel visible as NaN rather than a misleading -1e-13 s.
    df["tdc_dt_s"] = np.where(df["tdc_index"] >= 0,
                              df["tdc_dt"].astype("float64") *
                              TDC_SECONDS_PER_TICK, np.nan)
    df.attrs["tdc_reference"] = used
    df.attrs["tdc_from_file"] = bool(stored)
    return df
