import os
import re
import io
import hashlib
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import sys
import time
import signal
import threading

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import streamlit as st
import skrf as rf


# =========================
# Streamlit cache compatibility (older/newer versions)
# =========================
def _cache_resource_decorator():
    if hasattr(st, "cache_resource"):
        return st.cache_resource
    if hasattr(st, "experimental_singleton"):
        return st.experimental_singleton
    return lambda **kwargs: st.cache(allow_output_mutation=True, **kwargs)


def _cache_data_decorator():
    if hasattr(st, "cache_data"):
        return st.cache_data
    if hasattr(st, "experimental_memo"):
        return st.experimental_memo
    return st.cache

def _shutdown_server_soon(delay_s: float = 0.5):
    """
    Shut down the Streamlit process after a short delay.
    The delay gives the browser time to run the JS attempt to close/navigate away.
    """
    def _worker():
        time.sleep(delay_s)
        try:
            # Most graceful on Linux/macOS
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            # Guaranteed exit fallback (also works on Windows)
            os._exit(0)

    threading.Thread(target=_worker, daemon=True).start()



cache_resource = _cache_resource_decorator()
cache_data = _cache_data_decorator()


# =========================
# App config
# =========================
st.set_page_config(page_title="Touchstone Comparator", page_icon="📈", layout="wide")
st.title("Touchstone Comparator (.s2p / .sNp)")
st.caption(
    "Upload multiple Touchstone files, select traces per file, overlay on one plot, "
    "customize axis/title/legend, and export PNG/JPG/CSV."
)


# =========================
# Sidebar: UI sizing (browser-side) + upload/global options
# =========================
with st.sidebar:
    st.divider()
    st.header("App control")
    confirm_quit = st.checkbox("Confirm quit", value=False, help="Prevents accidental shutdown.")
    if st.button("Quit (stop server)", disabled=(not confirm_quit), use_container_width=True):
        st.session_state["_quit_requested"] = True

with st.sidebar:
    st.header("Display (browser/UI)")

    ui_scale_pct = st.slider(
        "UI scale (%)",
        min_value=60,
        max_value=110,
        value=70,
        step=5,
        help="Shrinks Streamlit UI text/widgets (CSS).",
    )

    max_content_width_px = st.slider(
        "Max content width (px)",
        min_value=700,
        max_value=1800,
        value=1050,
        step=50,
        help="Limits how wide plots/tables can expand in the browser.",
    )

# Apply CSS sizing constraints (this is what fixes “it fills my whole monitor”)
st.markdown(
    f"""
    <style>
      /* shrink UI typography */
      html, body, [data-testid="stAppViewContainer"] {{
        font-size: {ui_scale_pct}% !important;
      }}

      /* limit main content width even in wide layout */
      section.main > div.block-container {{
        max-width: {max_content_width_px}px !important;
        padding-left: 2rem;
        padding-right: 2rem;
      }}

      /* ensure matplotlib images don't stretch beyond max width */
      div[data-testid="stImage"] img {{
        max-width: {max_content_width_px}px !important;
        width: 100% !important;
        height: auto !important;
        display: block;
        margin-left: auto;
        margin-right: auto;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.divider()
    st.header("Upload")
    uploads = st.file_uploader(
        "Touchstone files (.s2p/.sNp)",
        type=None,
        accept_multiple_files=True,  # [Source](https://docs.streamlit.io/1.49.0/develop/api-reference/widgets/st.file_uploader)
        help="Upload multiple Touchstone files to compare.",
    )

    st.divider()
    st.header("Global options")
    unwrap_phase = st.toggle("Unwrap phase", value=True)
    mag_scale = st.radio("Magnitude scale", ["dB", "Linear"], index=0, horizontal=True)

if st.session_state.get("_quit_requested", False):
    st.warning("Shutting down… This tab may close; if not, you can close it manually.")
    # Attempt to close the tab and/or navigate away (browser may block window.close)
    st.markdown(
        """
        <script>
          try { window.open('', '_self'); window.close(); } catch (e) {}
          setTimeout(() => { window.location.href = 'about:blank'; }, 150);
        </script>
        """,
        unsafe_allow_html=True,
    )
    _shutdown_server_soon(0.6)
    st.stop()

# =========================
# Utilities
# =========================
_LABEL_RE = re.compile(r"^S\s*\(?\s*(\d+)\s*[,/_:]?\s*(\d+)\s*\)?\s*$", re.IGNORECASE)


def file_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def label_for(m: int, n: int, nports: int) -> str:
    # Avoid ambiguity for >9 ports
    if nports <= 9:
        return "S{}{}".format(m, n)
    return "S{},{}".format(m, n)


def parse_label(lbl: str) -> Tuple[int, int]:
    s = lbl.strip().replace(" ", "")
    if len(s) == 3 and s[0].upper() == "S" and s[1].isdigit() and s[2].isdigit():
        return int(s[1]), int(s[2])

    m = _LABEL_RE.match(s)
    if not m:
        raise ValueError("Bad trace label: {}".format(lbl))
    return int(m.group(1)), int(m.group(2))


def all_trace_labels(nports: int) -> List[str]:
    return [label_for(i, j, nports) for i in range(1, nports + 1) for j in range(1, nports + 1)]


@cache_resource(show_spinner=False)
def load_network_cached(file_hash: str, file_name: str, _raw: bytes) -> rf.Network:
    suffix = os.path.splitext(file_name)[1].lower()
    if not (suffix.startswith(".s") and suffix.endswith("p")):
        raise ValueError("Expected a Touchstone extension like .s2p, .s3p, ...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(_raw)
        tmp_path = f.name

    try:
        return rf.Network(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def interp_complex(f_src: np.ndarray, s_src: np.ndarray, f_dst: np.ndarray) -> np.ndarray:
    re_ = np.interp(f_dst, f_src, np.real(s_src), left=np.nan, right=np.nan)
    im_ = np.interp(f_dst, f_src, np.imag(s_src), left=np.nan, right=np.nan)
    return re_ + 1j * im_


def compute_metrics_from_s(f_hz: np.ndarray, s: np.ndarray, unwrap_phase: bool) -> Dict[str, np.ndarray]:
    mag = np.abs(s)
    mag_db = 20 * np.log10(np.maximum(mag, 1e-15))

    phase = np.angle(s)
    valid = np.isfinite(np.real(s)) & np.isfinite(np.imag(s))

    phase_unwrapped = np.full_like(phase, np.nan, dtype=float)
    if np.any(valid):
        ph = phase[valid]
        if unwrap_phase:
            ph = np.unwrap(ph)
        phase_unwrapped[valid] = ph

    phase_deg = np.degrees(phase_unwrapped)

    # group delay: - d(phi)/d(omega), omega = 2*pi*f
    omega = 2 * np.pi * f_hz
    gd_s = np.full_like(phase_unwrapped, np.nan, dtype=float)
    if np.sum(valid) >= 3:
        idx = np.where(valid)[0]
        phv = phase_unwrapped[idx]
        omv = omega[idx]
        gd_s[idx] = -np.gradient(phv, omv)

    gd_ns = gd_s * 1e9

    return {
        "mag": mag,
        "mag_dB": mag_db,
        "phase_deg": phase_deg,
        "group_delay_ns": gd_ns,
        "re": np.real(s),
        "im": np.imag(s),
    }


@dataclass(frozen=True)
class TraceSelection:
    file_hash: str
    file_label: str
    trace_label: str
    m: int
    n: int


def default_traces_for_nports(nports: int) -> List[str]:
    if nports == 2:
        return ["S11", "S21", "S12", "S22"]
    return [label_for(i, i, nports) for i in range(1, nports + 1)]


def apply_limits(
    ax,
    use_xlim: bool,
    xmin: Optional[float],
    xmax: Optional[float],
    use_ylim: bool,
    ymin: Optional[float],
    ymax: Optional[float],
    use_xstep: bool,
    xstep: Optional[float],
    use_ystep: bool,
    ystep: Optional[float],
):
    if use_xlim and xmin is not None and xmax is not None and xmin < xmax:
        ax.set_xlim(xmin, xmax)

    if use_ylim and ymin is not None and ymax is not None and ymin < ymax:
        ax.set_ylim(ymin, ymax)

    if use_xstep and xstep is not None and xstep > 0:
        ax.xaxis.set_major_locator(MultipleLocator(xstep))

    if use_ystep and ystep is not None and ystep > 0:
        ax.yaxis.set_major_locator(MultipleLocator(ystep))



LEGEND_LOCS = [
    "best",
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "center left",
    "center right",
    "upper center",
    "lower center",
    "center",
]


def make_overlay_figure(
    df: pd.DataFrame,
    y_col: str,
    title: str,
    xlabel: str,
    ylabel: str,
    use_xlim: bool,
    xmin: Optional[float],
    xmax: Optional[float],
    use_ylim: bool,
    ymin: Optional[float],
    ymax: Optional[float],
    use_xstep: bool,
    xstep: Optional[float],
    use_ystep: bool,
    ystep: Optional[float],
    legend_show: bool,
    legend_loc: str,
    legend_ncol: int,
    legend_fontsize: float,
    legend_frame: bool,
):
    fig, ax = plt.subplots()

    for (file_label, trace_label), g in df.groupby(["file_label", "trace_label"], sort=False):
        ax.plot(g["freq_GHz"], g[y_col], linewidth=2, label="{} · {}".format(file_label, trace_label))

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    apply_limits(
        ax,
        use_xlim, xmin, xmax,
        use_ylim, ymin, ymax,
        use_xstep, xstep,
        use_ystep, ystep,
    )

    # grid follows the major ticks
    ax.grid(True, which="major", alpha=0.25)

    if legend_show:
        ax.legend(
            fontsize=legend_fontsize,
            ncol=max(1, int(legend_ncol)),
            loc=legend_loc,
            frameon=legend_frame,
        )

    return fig


def fig_to_image_bytes(fig, fmt: str, dpi: int) -> bytes:
    buf = io.BytesIO()
    if fmt.lower() in ("jpg", "jpeg"):
        fig.savefig(buf, format="jpeg", dpi=dpi, bbox_inches="tight")
        return buf.getvalue()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    return buf.getvalue()


def plot_export_panel(
    df_for_plot: pd.DataFrame,
    fig,
    default_basename: str,
    y_col: str,
    png_dpi_default: int = 150,
):
    st.markdown("### Save as…")
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.4])

    with c1:
        save_type = st.selectbox("Type", ["png", "jpg", "csv"], index=0, key=default_basename + "_savetype")
    with c2:
        file_name = st.text_input(
            "File name",
            value="{}.{}".format(default_basename, save_type),
            key=default_basename + "_filename",
        )
    with c3:
        dpi = st.number_input(
            "PNG DPI",
            min_value=50,
            max_value=600,
            value=png_dpi_default,
            step=25,
            disabled=(save_type != "png"),
            key=default_basename + "_dpi",
            help="Only applies to PNG.",
        )
    with c4:
        if save_type in ("png", "jpg"):
            data = fig_to_image_bytes(fig, fmt=save_type, dpi=int(dpi) if save_type == "png" else 150)
            mime = "image/png" if save_type == "png" else "image/jpeg"
            st.download_button(
                "Download image",
                data=data,
                file_name=file_name,
                mime=mime,
                use_container_width=True,
                help="Triggers a browser download (acts like Save As).",
            )
        else:
            # WIDE / EXCEL-STYLE CSV:
            # index = frequency, columns = one column per curve (file_label · trace_label)
            wide = df_for_plot.pivot_table(
                index=["freq_Hz", "freq_GHz"],
                columns=["file_label", "trace_label"],
                values=y_col,
                aggfunc="first",
            )

            # Flatten MultiIndex columns into readable Excel headers
            wide.columns = ["{} · {}".format(fl, tr) for (fl, tr) in wide.columns]
            wide = wide.reset_index()

            csv_bytes = wide.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV (wide)",
                data=csv_bytes,
                file_name=file_name,
                mime="text/csv",
                use_container_width=True,
                help="Wide CSV: one column per curve, Excel-friendly.",
            )

# =========================
# Main: load + selections
# =========================
if not uploads:
    st.info("Upload one or more Touchstone files to begin.")
    st.stop()

# Load networks
files = []
for up in uploads:
    raw = up.getvalue()
    h = file_sha256(raw)
    ntwk = load_network_cached(h, up.name, raw)
    files.append({"name": up.name, "hash": h, "ntwk": ntwk, "nports": ntwk.nports})

st.success(
    "Loaded files:\n\n"
    + "\n".join(["- **{}** (ports={}, points={})".format(f["name"], f["nports"], len(f["ntwk"].f)) for f in files])
)

st.subheader("1) Select traces from each file to overlay")

selections = []  # type: List[TraceSelection]

for i, f in enumerate(files):
    file_label_default = os.path.splitext(os.path.basename(f["name"]))[0]
    with st.expander("File {}: {}".format(i + 1, f["name"]), expanded=(i == 0)):
        c1, c2 = st.columns([2, 3])
        with c1:
            file_label = st.text_input(
                "Legend label",
                value=file_label_default,
                key="filelabel_{}".format(f["hash"]),
            )
        with c2:
            trace_options = all_trace_labels(f["nports"])
            default_traces = default_traces_for_nports(f["nports"])
            chosen = st.multiselect(
                "Traces for this file",
                options=trace_options,
                default=[t for t in default_traces if t in trace_options],
                key="traces_{}".format(f["hash"]),
            )

        for t in chosen:
            m, n = parse_label(t)
            selections.append(TraceSelection(f["hash"], file_label, t, m, n))

if not selections:
    st.warning("Select at least one trace from at least one file.")
    st.stop()

# Frequency alignment: use first file grid
st.subheader("2) Frequency alignment + plot window")
st.radio("Frequency alignment", ["Use frequency grid of first file (recommended)"], index=0, horizontal=True)

f_common_hz = files[0]["ntwk"].f
f_common_ghz = f_common_hz / 1e9
fmin = float(np.nanmin(f_common_ghz))
fmax = float(np.nanmax(f_common_ghz))

freq_range = st.slider("Frequency range (GHz)", min_value=fmin, max_value=fmax, value=(fmin, fmax))
f_lo, f_hi = freq_range
mask_f = (f_common_ghz >= f_lo) & (f_common_ghz <= f_hi)
f_plot_hz = f_common_hz[mask_f]
f_plot_ghz = f_common_ghz[mask_f]
if len(f_plot_hz) < 2:
    st.error("Frequency range too narrow; expand the slider.")
    st.stop()

# Build long dataframe for all selected traces (interpolated to common grid)
rows = []
file_by_hash = {f["hash"]: f for f in files}

for sel in selections:
    f = file_by_hash[sel.file_hash]
    ntwk = f["ntwk"]

    m0, n0 = sel.m - 1, sel.n - 1
    s_src = ntwk.s[:, m0, n0]
    f_src = ntwk.f

    s_common = interp_complex(f_src, s_src, f_common_hz)
    s_plot = s_common[mask_f]
    metrics = compute_metrics_from_s(f_plot_hz, s_plot, unwrap_phase=unwrap_phase)

    df_one = pd.DataFrame(
        {
            "file_label": sel.file_label,
            "file_name": f["name"],
            "trace_label": sel.trace_label,
            "m": sel.m,
            "n": sel.n,
            "freq_Hz": f_plot_hz,
            "freq_GHz": f_plot_ghz,
            "re": metrics["re"],
            "im": metrics["im"],
            "mag": metrics["mag"],
            "mag_dB": metrics["mag_dB"],
            "phase_deg": metrics["phase_deg"],
            "group_delay_ns": metrics["group_delay_ns"],
        }
    )
    rows.append(df_one)

long_df = pd.concat(rows, ignore_index=True)

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["Magnitude", "Phase", "Group Delay", "Smith Chart"])

def plot_settings_block(prefix: str, default_title: str, default_ylabel: str):
    with st.expander("Plot settings", expanded=False):
        title = st.text_input("Title", value=default_title, key=prefix + "_title")
        xlabel = st.text_input("X label", value="Frequency (GHz)", key=prefix + "_xlabel")
        ylabel = st.text_input("Y label", value=default_ylabel, key=prefix + "_ylabel")

        st.markdown("**Axis limits**")
        c1, c2, c3 = st.columns(3)
        with c1:
            use_xlim = st.checkbox("Override X limits", value=False, key=prefix + "_use_xlim")
        with c2:
            xmin = st.number_input("X min (GHz)", value=float(f_lo), key=prefix + "_xmin")
        with c3:
            xmax = st.number_input("X max (GHz)", value=float(f_hi), key=prefix + "_xmax")

        c1, c2, c3 = st.columns(3)
        with c1:
            use_ylim = st.checkbox("Override Y limits", value=False, key=prefix + "_use_ylim")
        with c2:
            ymin = st.number_input("Y min", value=0.0, key=prefix + "_ymin")
        with c3:
            ymax = st.number_input("Y max", value=0.0, key=prefix + "_ymax")

        st.markdown("**Axis step / grid spacing**")
        c1, c2 = st.columns(2)
        with c1:
            use_xstep = st.checkbox("Use X step", value=False, key=prefix + "_use_xstep")
            xstep = st.number_input(
                "X step",
                min_value=0.000001,
                value=5.0,
                step=1.0,
                key=prefix + "_xstep",
                help="Major tick spacing on X axis. Example: 5 gives grid at 0, 5, 10, ...",
            )
        with c2:
            use_ystep = st.checkbox("Use Y step", value=False, key=prefix + "_use_ystep")
            ystep = st.number_input(
                "Y step",
                min_value=0.000001,
                value=5.0,
                step=1.0,
                key=prefix + "_ystep",
                help="Major tick spacing on Y axis.",
            )

        st.markdown("**Legend**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            legend_show = st.checkbox("Show legend", value=True, key=prefix + "_leg_show")
        with c2:
            legend_loc = st.selectbox("Location", options=LEGEND_LOCS, index=0, key=prefix + "_leg_loc")
        with c3:
            legend_ncol = st.slider("Columns", min_value=1, max_value=6, value=2, key=prefix + "_leg_ncol")
        with c4:
            legend_fontsize = st.number_input(
                "Font size",
                min_value=6.0,
                max_value=18.0,
                value=9.0,
                step=0.5,
                key=prefix + "_leg_fs",
            )

        legend_frame = st.checkbox("Legend frame", value=False, key=prefix + "_leg_frame")

    return (
        title,
        xlabel,
        ylabel,
        use_xlim,
        xmin,
        xmax,
        use_ylim,
        ymin,
        ymax,
        use_xstep,
        xstep,
        use_ystep,
        ystep,
        legend_show,
        legend_loc,
        legend_ncol,
        legend_fontsize,
        legend_frame,
    )


with tab1:
    y_col = "mag_dB" if mag_scale == "dB" else "mag"
    ylabel_default = "Magnitude (dB)" if mag_scale == "dB" else "Magnitude (linear)"

    settings = plot_settings_block("mag", "Magnitude overlay", ylabel_default)
    fig = make_overlay_figure(long_df, y_col, *settings)
    st.pyplot(fig, clear_figure=False)
    plot_export_panel(long_df, fig, default_basename="magnitude_overlay", y_col=y_col, png_dpi_default=200)
    plt.close(fig)

with tab2:
    settings = plot_settings_block("ph", "Phase overlay" + (" (unwrapped)" if unwrap_phase else ""), "Phase (deg)")
    fig = make_overlay_figure(long_df, "phase_deg", *settings)
    st.pyplot(fig, clear_figure=False)
    plot_export_panel(long_df, fig, default_basename="phase_overlay", y_col="phase_deg", png_dpi_default=200)
    plt.close(fig)

with tab3:
    settings = plot_settings_block("gd", "Group delay overlay", "Group delay (ns)")
    fig = make_overlay_figure(long_df, "group_delay_ns", *settings)
    st.pyplot(fig, clear_figure=False)
    plot_export_panel(long_df, fig, default_basename="group_delay_overlay", y_col="group_delay_ns", png_dpi_default=200)
    plt.close(fig)

with tab4:
    st.caption("Smith chart is most meaningful for reflection terms (S11, S22, ...).")
    selected_unique = long_df[["file_label", "trace_label"]].drop_duplicates()

    reflection_rows = selected_unique[selected_unique["trace_label"].apply(lambda t: parse_label(t)[0] == parse_label(t)[1])]
    default_rows = reflection_rows if len(reflection_rows) else selected_unique.head(1)

    smith_pick = st.multiselect(
        "Choose file+trace curves to draw",
        options=["{} · {}".format(r.file_label, r.trace_label) for r in selected_unique.itertuples(index=False)],
        default=["{} · {}".format(r.file_label, r.trace_label) for r in default_rows.itertuples(index=False)],
    )

    if not smith_pick:
        st.info("Pick at least one curve.")
    else:
        fig, ax = plt.subplots(figsize=(6.5, 6.5))
        rf.plotting.smith(ax=ax)

        for key in smith_pick:
            file_label, trace_label = [s.strip() for s in key.split("·")]
            g = long_df[(long_df["file_label"] == file_label) & (long_df["trace_label"] == trace_label)].copy()
            s = g["re"].to_numpy() + 1j * g["im"].to_numpy()
            rf.plotting.plot_smith(s, ax=ax, label="{} · {}".format(file_label, trace_label))

        ax.set_title("Smith chart overlay")
        ax.legend(fontsize=9, loc="best", frameon=False)
        st.pyplot(fig, clear_figure=False)

        # Save-as for Smith: export an image; CSV export here isn't very meaningful (complex plane),
        # but if you want it, we can add it.
        st.markdown("### Save as…")
        fmt = st.selectbox("Type", ["png", "jpg"], index=0, key="smith_fmt")
        dpi = st.number_input("PNG DPI", min_value=50, max_value=600, value=200, step=25, disabled=(fmt != "png"), key="smith_dpi")
        fname = st.text_input("File name", value="smith_chart.{}".format(fmt), key="smith_fname")
        img_bytes = fig_to_image_bytes(fig, fmt=fmt, dpi=int(dpi) if fmt == "png" else 150)
        st.download_button(
            "Download image",
            data=img_bytes,
            file_name=fname,
            mime="image/png" if fmt == "png" else "image/jpeg",
            help="This triggers a browser download (acts like Save As).",
        )  # [Source](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button)

        plt.close(fig)
