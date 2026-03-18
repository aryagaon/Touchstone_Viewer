import os
import tempfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import skrf as rf


st.set_page_config(page_title="Touchstone Viewer", page_icon="📈", layout="wide")
st.title("Touchstone Viewer (.s2p / .sNp)")
st.caption("Upload a Touchstone file, overlay multiple S-parameters, view magnitude/phase/group delay/Smith chart, export CSV.")


# -------------------- Helpers --------------------

@st.cache_data(show_spinner=False)
def load_network_from_bytes(file_name: str, raw: bytes) -> rf.Network:
    """
    scikit-rf loads Touchstone reliably from a path; write bytes to temp file.
    """
    suffix = os.path.splitext(file_name)[1].lower()
    if not (suffix.startswith(".s") and suffix.endswith("p")):
        raise ValueError("Expected a Touchstone extension like .s2p, .s3p, ...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(raw)
        tmp_path = f.name

    try:
        return rf.Network(tmp_path)  # Touchstone -> Network [Source](https://scikit-rf.readthedocs.io/en/v1.8.0/tutorials/Networks.html)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def all_trace_labels(nports: int) -> list[str]:
    return [f"S{i}{j}" for i in range(1, nports + 1) for j in range(1, nports + 1)]


def parse_trace_label(label: str) -> tuple[int, int]:
    # label like "S21" => (m0, n0) zero-based
    if not label.startswith("S") or len(label) < 3:
        raise ValueError(f"Bad trace label: {label}")
    m = int(label[1]) - 1
    n = int(label[2]) - 1
    return m, n


def make_wide_df(ntwk: rf.Network, traces: list[str], unwrap_phase: bool) -> pd.DataFrame:
    f_hz = ntwk.f
    df = pd.DataFrame({"freq_Hz": f_hz, "freq_GHz": f_hz / 1e9})

    for t in traces:
        m0, n0 = parse_trace_label(t)
        s = ntwk.s[:, m0, n0]

        mag = np.abs(s)
        mag_db = 20 * np.log10(np.maximum(mag, 1e-15))

        phase = np.angle(s)
        if unwrap_phase:
            phase = np.unwrap(phase)
        phase_deg = np.degrees(phase)

        gd_ns = (ntwk.group_delay[:, m0, n0] * 1e9)  # [Source](https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.network.Network.group_delay.html)

        df[f"{t}_re"] = np.real(s)
        df[f"{t}_im"] = np.imag(s)
        df[f"{t}_mag"] = mag
        df[f"{t}_mag_dB"] = mag_db
        df[f"{t}_phase_deg"] = phase_deg
        df[f"{t}_group_delay_ns"] = gd_ns

    return df


def make_long_df(wide_df: pd.DataFrame, traces: list[str]) -> pd.DataFrame:
    rows = []
    base = wide_df[["freq_Hz", "freq_GHz"]].copy()

    for t in traces:
        tmp = base.copy()
        tmp["trace"] = t
        tmp["re"] = wide_df[f"{t}_re"]
        tmp["im"] = wide_df[f"{t}_im"]
        tmp["mag"] = wide_df[f"{t}_mag"]
        tmp["mag_dB"] = wide_df[f"{t}_mag_dB"]
        tmp["phase_deg"] = wide_df[f"{t}_phase_deg"]
        tmp["group_delay_ns"] = wide_df[f"{t}_group_delay_ns"]
        rows.append(tmp)

    return pd.concat(rows, ignore_index=True)


# -------------------- Sidebar UI --------------------

with st.sidebar:
    st.header("Upload")
    uploaded = st.file_uploader(
        "Touchstone file",
        type=None,  # accept .s2p/.sNp; validate ourselves [Source](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)
        help="Upload .s2p, .s3p, ... Touchstone files.",
    )

    st.divider()
    st.header("Overlay selection")
    unwrap_phase = st.toggle("Unwrap phase", value=True)
    mag_scale = st.radio("Magnitude scale", ["dB", "Linear"], index=0, horizontal=True)

    st.caption("Presets are shortcuts; you can always customize afterward.")


if not uploaded:
    st.info("Upload a .s2p / .sNp file to begin.")
    st.stop()

# Load Network
try:
    raw = uploaded.getvalue()
    ntwk = load_network_from_bytes(uploaded.name, raw)
except Exception as e:
    st.error(f"Could not read Touchstone file: {e}")
    st.stop()

nports = ntwk.nports
npoints = len(ntwk.f)

st.success(f"Loaded: **{uploaded.name}** | Ports: **{nports}** | Points: **{npoints}**")

# -------------------- Trace picking --------------------

labels = all_trace_labels(nports)

# Default selection: common 2-port set if N=2, otherwise reflections.
if nports == 2:
    default_traces = ["S11", "S21", "S12", "S22"]
else:
    default_traces = [f"S{i}{i}" for i in range(1, nports + 1)]

preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
with preset_col1:
    preset_reflections = st.button("Preset: Reflections")
with preset_col2:
    preset_common2p = st.button("Preset: 2-port common")
with preset_col3:
    preset_all = st.button("Preset: All")
with preset_col4:
    preset_clear = st.button("Clear")

if "selected_traces" not in st.session_state:
    st.session_state.selected_traces = default_traces

if preset_reflections:
    st.session_state.selected_traces = [f"S{i}{i}" for i in range(1, nports + 1)]
if preset_common2p:
    st.session_state.selected_traces = ["S11", "S21", "S12", "S22"] if nports == 2 else st.session_state.selected_traces
if preset_all:
    # Be careful with huge N; still allow but warn later.
    st.session_state.selected_traces = labels
if preset_clear:
    st.session_state.selected_traces = []

selected_traces = st.multiselect(
    "Select S-parameters to overlay",
    options=labels,
    default=st.session_state.selected_traces,
    help="Choose multiple traces to overlay on plots (magnitude/phase/group delay).",
)
st.session_state.selected_traces = selected_traces

if not selected_traces:
    st.warning("Select at least one trace to plot/export.")
    st.stop()

if len(selected_traces) > 16:
    st.warning("You selected many traces. Plots may become cluttered; consider using presets or fewer traces.")

# -------------------- Compute Data --------------------

wide_df = make_wide_df(ntwk, selected_traces, unwrap_phase=unwrap_phase)
long_df = make_long_df(wide_df, selected_traces)

# -------------------- Plot Tabs --------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Magnitude", "Phase", "Group Delay", "Smith Chart", "Export"])

with tab1:
    fig, ax = plt.subplots()
    x = wide_df["freq_GHz"].to_numpy()

    for t in selected_traces:
        y = wide_df[f"{t}_mag_dB"].to_numpy() if mag_scale == "dB" else wide_df[f"{t}_mag"].to_numpy()
        ax.plot(x, y, linewidth=2, alpha=0.9, label=t)

    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Magnitude (dB)" if mag_scale == "dB" else "Magnitude (linear)")
    ax.grid(True, alpha=0.3)
    ax.set_title("Magnitude overlay")
    ax.legend(ncol=4, fontsize=9)
    st.pyplot(fig, clear_figure=True)

with tab2:
    fig, ax = plt.subplots()
    x = wide_df["freq_GHz"].to_numpy()

    for t in selected_traces:
        ax.plot(x, wide_df[f"{t}_phase_deg"].to_numpy(), linewidth=2, alpha=0.9, label=t)

    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Phase (deg)")
    ax.grid(True, alpha=0.3)
    ax.set_title("Phase overlay" + (" (unwrapped)" if unwrap_phase else ""))
    ax.legend(ncol=4, fontsize=9)
    st.pyplot(fig, clear_figure=True)

with tab3:
    fig, ax = plt.subplots()
    x = wide_df["freq_GHz"].to_numpy()

    for t in selected_traces:
        ax.plot(x, wide_df[f"{t}_group_delay_ns"].to_numpy(), linewidth=2, alpha=0.9, label=t)

    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Group delay (ns)")
    ax.grid(True, alpha=0.3)
    ax.set_title("Group delay overlay")
    ax.legend(ncol=4, fontsize=9)
    st.pyplot(fig, clear_figure=True)

with tab4:
    st.caption("Smith charts get busy fast. By default, this plots only reflection terms among your selection (S11, S22, ...).")

    reflection_traces = [t for t in selected_traces if t[1] == t[2]]
    smith_traces = reflection_traces if reflection_traces else selected_traces[:1]

    smith_traces = st.multiselect(
        "Traces to draw on Smith chart",
        options=selected_traces,
        default=smith_traces,
        help="Typically plot reflections (S11, S22, ...).",
    )

    if not smith_traces:
        st.info("Pick at least one trace for Smith chart.")
    else:
        fig, ax = plt.subplots(figsize=(6.5, 6.5))
        for t in smith_traces:
            m0, n0 = parse_trace_label(t)
            # scikit-rf smith plotting [Source](https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.network.Network.plot_s_smith.html)
            ntwk.plot_s_smith(m=m0, n=n0, ax=ax, show_legend=False, linewidth=2, alpha=0.95)

        ax.set_title("Smith chart overlay")
        # Manual legend (since plot_s_smith doesn't label lines consistently)
        for t in smith_traces:
            ax.plot([], [], label=t)
        ax.legend(ncol=3, fontsize=9)
        st.pyplot(fig, clear_figure=True)

with tab5:
    st.subheader("CSV export (all selected traces)")

    export_format = st.radio(
        "Export format",
        ["Wide (one row per frequency)", "Long/Tidy (one row per frequency per trace)"],
        index=0,
        horizontal=True,
        help="Wide is convenient for Excel; Long is convenient for analysis/pivoting.",
    )

    if export_format.startswith("Wide"):
        export_df = wide_df
        default_name = f"{os.path.splitext(uploaded.name)[0]}_selected_traces_wide.csv"
    else:
        export_df = long_df
        default_name = f"{os.path.splitext(uploaded.name)[0]}_selected_traces_long.csv"

    st.caption("Preview")
    st.dataframe(export_df.head(200), use_container_width=True, height=300)

    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=default_name,
        mime="text/csv",
        help="Downloads the currently selected export format.",
    )  # [Source](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button)