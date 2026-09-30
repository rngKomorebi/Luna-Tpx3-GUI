"""Output naming: measurement metadata -> filename template -> .hdf5 name.

Also the Job record the queue is built from. Qt-free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

TEMPLATE_HELP = ("{stem} {measurement} {campaign} {date} {time} {datetime} "
                 "{comment} {bias} {exposure} {ntrig} {frames} {duration} "
                 "{polarity} {trigmode} {period} {chip} {chipboard} {size} "
                 "{thr_coarse} {thr_fine}")

# Default output name. Built from measurement_metadata.json in the folder above
# the .tpx3, so the result says what the run was instead of repeating ASI's
# four random characters. {stem} stays on the end: {date}+{comment} alone is
# not unique (several runs a day share a comment), and keeping the stem means
# every output can still be traced back to its raw file.
DEFAULT_TEMPLATE = "{date}_{time}_{comment}_{stem}"
# Every default this program has ever shipped. A saved template matching any of
# them was never a deliberate choice, so it is safe to move forward; anything
# else the user typed themselves and is left alone.
_SUPERSEDED_DEFAULTS = ("{stem}", "{date}_{comment}_{stem}")
TEMPLATE_VERSION = 3


def migrate_template(cfg) -> bool:
    """One-time move of an existing config onto the new default name.

    Without this the change would only reach fresh installs, since a saved
    config always carries an explicit "template". Runs once (guarded by
    template_version) and only when the saved value is a superseded default, so
    a deliberate choice of "{stem}" is never overwritten.
    """
    if cfg.get("template_version", 0) >= TEMPLATE_VERSION:
        return False
    cfg["template_version"] = TEMPLATE_VERSION
    if cfg.get("template", _SUPERSEDED_DEFAULTS[0]) in _SUPERSEDED_DEFAULTS:
        cfg["template"] = DEFAULT_TEMPLATE
        return True
    return False

PRESET_TEMPLATES = [
    ("{date}_{time}_{comment}_{stem}",
     "2026-08-07_12-52-45_DCR-0V-gain_fCqk_000000.hdf5  (default)"),
    ("{date}_{comment}_{stem}", "2026-08-07_DCR-0V-gain_fCqk_000000.hdf5"),
    ("{datetime}_{comment}", "2026-08-07_12-52-45_DCR-0V-gain.hdf5"),
    ("{date}_{time}_{comment}_{bias}V_{stem}",
     "2026-08-07_12-52-45_DCR-0V-gain_50V_fCqk_000000.hdf5"),
    ("{date}_{comment}_{frames}f_{duration}_{stem}",
     "2026-08-07_DCR-0V-gain_100f_10s_fCqk_000000.hdf5"),
    ("{measurement}", "Measurement_Aug_07_2026_12h52m45s.hdf5"),
    ("{campaign}_{measurement}", "data_DCR_07.08.2026_Measurement_....hdf5"),
    ("{stem}", "mirror the input name -- fCbh_000000.hdf5"),
]

def sanitize(text) -> str:
    """Make a value safe to drop into a filename.

    Returns "" for empty/unusable input so that an absent field simply drops
    out of the name template instead of leaving a placeholder behind.
    """
    out = re.sub(r"[^A-Za-z0-9._+-]+", "-", str(text).strip())
    return out.strip("-._")

# ---------------------------------------------------------------------------
# measurement metadata -> filename fields
# ---------------------------------------------------------------------------

def measurement_context(tpx3: Path) -> dict:
    """Collect naming fields for one .tpx3 file.

    ASI writes  <campaign>/<Measurement_...>/raw/<file>.tpx3  with
    measurement_metadata.json and comment.txt in the measurement folder, so we
    walk up a few levels looking for them.
    """
    ctx = {"stem": tpx3.stem, "measurement": "", "campaign": "", "date": "",
           "time": "", "datetime": "", "comment": "", "bias": "",
           "exposure": "", "ntrig": "", "chip": "", "frames": "",
           "duration": "", "polarity": "", "trigmode": "", "period": "",
           "chipboard": "", "size": "", "thr_coarse": "", "thr_fine": ""}

    meta_dir = None
    for up in [tpx3.parent] + list(tpx3.parents)[1:4]:
        if (up / "measurement_metadata.json").is_file() or (up / "comment.txt").is_file():
            meta_dir = up
            break
    if meta_dir is None:
        p = tpx3.parent
        meta_dir = p.parent if p.name.lower() == "raw" else p
    ctx["measurement"] = meta_dir.name
    ctx["campaign"] = meta_dir.parent.name

    cfile = meta_dir / "comment.txt"
    if cfile.is_file():
        try:
            ctx["comment"] = sanitize(cfile.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass

    mfile = meta_dir / "measurement_metadata.json"
    if mfile.is_file():
        try:
            meta = json.loads(mfile.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            meta = {}
        stamp = str(meta.get("StartDateTime", ""))
        if "T" in stamp:
            d, _, t = stamp.partition("T")
            ctx["date"] = d
            ctx["time"] = t.split(".")[0].replace(":", "-")
            ctx["datetime"] = ctx["date"] + "_" + ctx["time"]
        # The JSON carries the comment as well, and it is the authoritative
        # copy -- comment.txt is only a convenience file written beside it.
        if meta.get("CommentAtTimeOfMeasurement"):
            ctx["comment"] = sanitize(meta["CommentAtTimeOfMeasurement"])
        if meta.get("NumberOfFrames") is not None:
            ctx["frames"] = sanitize(meta["NumberOfFrames"])
        stop = str(meta.get("StopDateTime", ""))
        if "T" in stamp and "T" in stop:
            try:
                secs = (datetime.fromisoformat(stop)
                        - datetime.fromisoformat(stamp)).total_seconds()
                ctx["duration"] = sanitize(f"{secs:.0f}s" if secs >= 1
                                           else f"{secs * 1000:.0f}ms")
            except Exception:
                pass

        det = meta.get("Detector") or {}
        conf = det.get("Config") or {}
        for key, src in (("bias", "BiasVoltage"), ("exposure", "ExposureTime"),
                         ("ntrig", "nTriggers"), ("polarity", "Polarity"),
                         ("trigmode", "TriggerMode"), ("period", "TriggerPeriod")):
            if src in conf:
                ctx[key] = sanitize(conf[src])

        layout = det.get("Layout") or {}
        if layout.get("Width") and layout.get("Height"):
            ctx["size"] = f"{layout['Width']}x{layout['Height']}"

        boards = (det.get("Info") or {}).get("Boards") or []
        if boards:
            if boards[0].get("ChipboardId"):
                ctx["chipboard"] = sanitize(boards[0]["ChipboardId"])
            named = [c.get("Name", "") for c in (boards[0].get("Chips") or [])
                     if c.get("Name") and not str(c["Name"]).startswith("W0000")]
            if named:
                ctx["chip"] = sanitize(named[0])

        # Threshold DACs. WARNING: on at least some Serval versions these are
        # written once at acquisition start and do NOT track a per-measurement
        # threshold change -- three runs at different thresholds can all report
        # the same pair. Check them against your own data before naming files
        # by them; the comment field is usually the reliable discriminator.
        dacs = det.get("DACs") or []
        if dacs:
            for key, src in (("thr_coarse", "Vthreshold_coarse"),
                             ("thr_fine", "Vthreshold_fine")):
                if src in dacs[0]:
                    ctx[key] = sanitize(dacs[0][src])
    return ctx


def render_name(template: str, ctx: dict) -> str:
    """Expand a filename template, dropping unknown placeholders gracefully."""
    class _Safe(dict):
        def __missing__(self, key):
            return ""
    try:
        name = template.format_map(_Safe(ctx))
    except Exception:
        name = ctx["stem"]
    name = re.sub(r"([_.-])\1+", r"\1", name).strip("_-. ")
    return name or ctx["stem"]


# ---------------------------------------------------------------------------
# the job queue
# ---------------------------------------------------------------------------

@dataclass
class Job:
    src: Path
    dst: Path = None
    status: str = "queued"
    note: str = ""
    ctx: dict = field(default_factory=dict)
    origin: str = ""          # batch folder this came from, "" if added by hand
    overwrite: bool = False   # redo this one even though its .hdf5 exists
