"""Plot constants and matplotlib styling for the Inspect tab.

Qt-free. matplotlib and komorebi_mpl are optional and imported lazily, inside
plot_style_context(), so importing this module costs nothing.
"""

from __future__ import annotations

import contextlib

# Timepix3 clocks ToT on the 40 MHz reference, so every tot / ctot value in the
# HDF5 is an exact multiple of 25 ns. Histogram bin widths must be integer
# multiples of this or the bins beat against the level spacing.
TOT_LSB_NS = 25.0

# Clusters/sum_tot reaches ~227 us, so the native 25 ns tick would be ~9000
# bins. Snap to a whole number of ticks aiming for roughly this many instead.
STOT_TARGET_BINS = 300

# Cluster size histogram: one bin per pixel over 0..40, which is where the
# distribution lives -- anything above is counted and reported in the title
# rather than dropped without saying so.
CSIZE_MAX = 40
CSIZE_BINS = 40

# Plot styles from komorebi_mpl, one per app theme. Importing the package
# registers them with matplotlib; if it is not installed the plots fall back to
# colouring themselves from the app palette (see plot_style_context).
KOMOREBI_STYLES = {"dark": "night_wave", "light": "sci_pure"}

# Window titles for the Inspect tab's plots, so several open at once stay
# tellable apart from the taskbar.
PLOT_TITLES = {
    "hitmap": "Hitmap, pixels",
    "cmap": "Hitmap, clusters",
    "tot": "ToT, peak pixel",
    "stot": "ToT, cluster total",
    "csize": "Cluster size histogram",
    "tdc": "Time since TDC edge",
}

# The komorebi styles are authored for a 16x10 in export figure: 30 pt text and
# 10 pt tick marks. Dropped unscaled onto the ~6.6 in on-screen canvas that is
# roughly 2.4x too large, so the point sizes get scaled by the figure-width
# ratio. Colours, cyclers and colormaps are left exactly as the style set them.
PLOT_FIGSIZE = (6.6, 5.4)
_SCALED_RC = ("font.size", "axes.titlesize", "axes.labelsize", "xtick.labelsize",
              "ytick.labelsize", "legend.fontsize", "legend.title_fontsize",
              "figure.titlesize", "figure.labelsize",
              "xtick.major.size", "ytick.major.size",
              "xtick.minor.size", "ytick.minor.size", "axes.titlepad",
              "axes.labelpad", "xtick.major.pad", "ytick.major.pad")
_MIN_PT = 4.0

# figure.frameon=False is right for an export onto a white page -- it leaves the
# figure patch undrawn so the paper shows through. On screen the canvas behind
# it is white, so a dark style renders dark text on white and is unreadable.
# The colour is already correct; it just has to actually be painted.
# axes.grid is off deliberately: these are dense hitmaps and long-tailed
# histograms, where a grid competes with the data rather than helping read it.
_ONSCREEN_FIXED = {"figure.figsize": PLOT_FIGSIZE, "figure.frameon": True,
                   "axes.grid": False}


def onscreen_overrides(style_rc):
    """Point sizes from a big-figure style, rescaled for the on-screen figure."""
    try:
        base_w = float(style_rc["figure.figsize"][0])
    except Exception:
        return {}
    if base_w <= 0:
        return {}
    k = PLOT_FIGSIZE[0] / base_w
    if 0.95 <= k <= 1.05:                  # already sized for the screen
        return dict(_ONSCREEN_FIXED)
    out = dict(_ONSCREEN_FIXED)
    for key in _SCALED_RC:
        v = style_rc.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = max(_MIN_PT, float(v) * k)
    return out


def plot_style_context(theme_name):
    """A matplotlib style context for the current app theme.

    Returns (context_manager, styled). When komorebi_mpl is missing -- it is an
    optional dependency -- this hands back a null context and False, and the
    caller paints the figure from the app palette instead, exactly as before.
    """
    name = KOMOREBI_STYLES.get(theme_name)
    if name:
        try:
            import komorebi_mpl                      # noqa: F401  registers them
            import matplotlib.pyplot as plt
            if name in plt.style.available:
                overrides = onscreen_overrides(plt.style.library[name])
                return plt.style.context([name, overrides]), True
        except Exception:
            pass
    return contextlib.nullcontext(), False
