"""
Real Exchange Rate Explorer (IMF data)
======================================

Streamlit app that pulls monthly CPI and exchange-rate data from the IMF SDMX 3.0
API and computes, for any pair of countries (or the Euro area):

    S(t)    = units of Country 2 currency per one unit of Country 1 currency
    RER(t)  = S(t) * P1(t) / P2(t)
    RER*    = average of RER(t) over valid months in the selected sample
    Real Index(t) = 100 * RER(t) / RER*

Python 3.12 compatible.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
IMF_BASE = "https://api.imf.org/external/sdmx/3.0"
CPI_FLOW = "IMF.STA/CPI"      # key: {ISO3}.CPI._T.IX.M
ER_FLOW = "IMF.STA/ER"        # key: {ISO3}.XDC_USD.PA_RT.M  (local currency per USD)
START_YEAR = 1976
REQUEST_TIMEOUT = 60

PURPLE_BG = "#4E2A84"         # Northwestern purple
PURPLE_DARK = "#401F68"
PURPLE_LIGHT = "#B6ACD1"

# Place the official logo file in the repo (see README). First match is used.
LOGO_CANDIDATES = [
    "assets/kellogg_logo.png",
    "assets/kellogg_logo.svg",
    "assets/kellogg_logo.jpg",
    "assets/kellogg_logo.jpeg",
    "assets/kellogg_logo.webp",
    "kellogg_logo.png",
    "kellogg_logo.svg",
]

# IMF country list (ISO3 -> name) plus the Euro area aggregate (G163).
COUNTRIES: dict[str, str] = {
    "G163": "Euro area",
    "AFG": "Afghanistan", "ALB": "Albania", "DZA": "Algeria", "AGO": "Angola",
    "ATG": "Antigua and Barbuda", "ARG": "Argentina", "ARM": "Armenia",
    "ABW": "Aruba", "AUS": "Australia", "AUT": "Austria", "AZE": "Azerbaijan",
    "BHS": "Bahamas, The", "BHR": "Bahrain", "BGD": "Bangladesh",
    "BRB": "Barbados", "BLR": "Belarus", "BEL": "Belgium", "BLZ": "Belize",
    "BEN": "Benin", "BTN": "Bhutan", "BOL": "Bolivia",
    "BIH": "Bosnia and Herzegovina", "BWA": "Botswana", "BRA": "Brazil",
    "BRN": "Brunei Darussalam", "BGR": "Bulgaria", "BFA": "Burkina Faso",
    "BDI": "Burundi", "CPV": "Cabo Verde", "KHM": "Cambodia", "CMR": "Cameroon",
    "CAN": "Canada", "CAF": "Central African Republic", "TCD": "Chad",
    "CHL": "Chile", "CHN": "China, P.R.: Mainland", "HKG": "China, P.R.: Hong Kong",
    "MAC": "China, P.R.: Macao", "COL": "Colombia", "COM": "Comoros",
    "COD": "Congo, Democratic Republic of the", "COG": "Congo, Republic of",
    "CRI": "Costa Rica", "CIV": "Côte d'Ivoire", "HRV": "Croatia",
    "CUW": "Curaçao", "CYP": "Cyprus", "CZE": "Czech Republic", "DNK": "Denmark",
    "DJI": "Djibouti", "DMA": "Dominica", "DOM": "Dominican Republic",
    "ECU": "Ecuador", "EGY": "Egypt", "SLV": "El Salvador",
    "GNQ": "Equatorial Guinea", "ERI": "Eritrea", "EST": "Estonia",
    "SWZ": "Eswatini", "ETH": "Ethiopia", "FJI": "Fiji", "FIN": "Finland",
    "FRA": "France", "GAB": "Gabon", "GMB": "Gambia, The", "GEO": "Georgia",
    "DEU": "Germany", "GHA": "Ghana", "GRC": "Greece", "GRD": "Grenada",
    "GTM": "Guatemala", "GIN": "Guinea", "GNB": "Guinea-Bissau", "GUY": "Guyana",
    "HTI": "Haiti", "HND": "Honduras", "HUN": "Hungary", "ISL": "Iceland",
    "IND": "India", "IDN": "Indonesia", "IRN": "Iran", "IRQ": "Iraq",
    "IRL": "Ireland", "ISR": "Israel", "ITA": "Italy", "JAM": "Jamaica",
    "JPN": "Japan", "JOR": "Jordan", "KAZ": "Kazakhstan", "KEN": "Kenya",
    "KIR": "Kiribati", "KOR": "Korea, Republic of", "XKX": "Kosovo",
    "KWT": "Kuwait", "KGZ": "Kyrgyz Republic", "LAO": "Lao P.D.R.",
    "LVA": "Latvia", "LBN": "Lebanon", "LSO": "Lesotho", "LBR": "Liberia",
    "LBY": "Libya", "LTU": "Lithuania", "LUX": "Luxembourg", "MDG": "Madagascar",
    "MWI": "Malawi", "MYS": "Malaysia", "MDV": "Maldives", "MLI": "Mali",
    "MLT": "Malta", "MHL": "Marshall Islands", "MRT": "Mauritania",
    "MUS": "Mauritius", "MEX": "Mexico", "FSM": "Micronesia, Fed. States of",
    "MDA": "Moldova", "MNG": "Mongolia", "MNE": "Montenegro", "MAR": "Morocco",
    "MOZ": "Mozambique", "MMR": "Myanmar", "NAM": "Namibia", "NRU": "Nauru",
    "NPL": "Nepal", "NLD": "Netherlands", "NZL": "New Zealand", "NIC": "Nicaragua",
    "NER": "Niger", "NGA": "Nigeria", "MKD": "North Macedonia", "NOR": "Norway",
    "OMN": "Oman", "PAK": "Pakistan", "PLW": "Palau", "PAN": "Panama",
    "PNG": "Papua New Guinea", "PRY": "Paraguay", "PER": "Peru",
    "PHL": "Philippines", "POL": "Poland", "PRT": "Portugal", "QAT": "Qatar",
    "ROU": "Romania", "RUS": "Russian Federation", "RWA": "Rwanda",
    "WSM": "Samoa", "SMR": "San Marino", "STP": "São Tomé and Príncipe",
    "SAU": "Saudi Arabia", "SEN": "Senegal", "SRB": "Serbia", "SYC": "Seychelles",
    "SLE": "Sierra Leone", "SGP": "Singapore", "SXM": "Sint Maarten",
    "SVK": "Slovak Republic", "SVN": "Slovenia", "SLB": "Solomon Islands",
    "SOM": "Somalia", "ZAF": "South Africa", "SSD": "South Sudan", "ESP": "Spain",
    "LKA": "Sri Lanka", "KNA": "St. Kitts and Nevis", "LCA": "St. Lucia",
    "VCT": "St. Vincent and the Grenadines", "SDN": "Sudan", "SUR": "Suriname",
    "SWE": "Sweden", "CHE": "Switzerland", "SYR": "Syria", "TWN": "Taiwan",
    "TJK": "Tajikistan", "TZA": "Tanzania", "THA": "Thailand",
    "TLS": "Timor-Leste", "TGO": "Togo", "TON": "Tonga",
    "TTO": "Trinidad and Tobago", "TUN": "Tunisia", "TUR": "Türkiye",
    "TKM": "Turkmenistan", "TUV": "Tuvalu", "UGA": "Uganda", "UKR": "Ukraine",
    "ARE": "United Arab Emirates", "GBR": "United Kingdom",
    "USA": "United States", "URY": "Uruguay", "UZB": "Uzbekistan",
    "VUT": "Vanuatu", "VEN": "Venezuela", "VNM": "Vietnam",
    "PSE": "West Bank and Gaza", "YEM": "Yemen", "ZMB": "Zambia", "ZWE": "Zimbabwe",
}


# --------------------------------------------------------------------------- #
# Page styling
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Real Exchange Rate Explorer",
    page_icon="💱",
    layout="wide",
)


def _find_logo() -> Path | None:
    base = Path(__file__).parent
    for rel in LOGO_CANDIDATES:
        p = base / rel
        if p.exists():
            return p
    return None


def _logo_data_uri(path: Path) -> str:
    mime = {
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


THEME_CSS = """
<style>
.stApp {
    background: linear-gradient(180deg, __PURPLE_BG__ 0%, __PURPLE_DARK__ 100%);
    color: #FFFFFF;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: __PURPLE_DARK__; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp label,
.stApp li, .stApp span, .stApp div[data-testid="stMarkdownContainer"],
.stApp [data-testid="stWidgetLabel"] p {
    color: #FFFFFF;
}
/* keep text readable inside inputs / dropdowns */
.stApp div[data-baseweb="select"] *, .stApp input { color: #1b1b1b !important; }
.stApp div[data-baseweb="select"] > div { background-color: #FFFFFF; }
.stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricLabel"] p {
    color: #FFFFFF;
}
.stDownloadButton button, .stButton button {
    background-color: #FFFFFF; color: __PURPLE_BG__; border: 0; font-weight: 600;
}
.stDownloadButton button p { color: __PURPLE_BG__ !important; }
.logo-card {
    background: #FFFFFF; border-radius: 10px; padding: 10px 18px;
    display: inline-block; margin-bottom: 8px;
}
.logo-card img { height: 56px; display: block; }
.logo-fallback {
    color: __PURPLE_BG__ !important; font-weight: 700; font-size: 1.2rem;
}
.plot-card { background: #FFFFFF; border-radius: 10px; padding: 6px; }
</style>
"""


def apply_theme() -> None:
    css = THEME_CSS.replace("__PURPLE_BG__", PURPLE_BG).replace("__PURPLE_DARK__", PURPLE_DARK)
    st.markdown(css, unsafe_allow_html=True)


def render_header() -> None:
    logo = _find_logo()
    if logo is not None:
        st.markdown(
            f'<div class="logo-card"><img src="{_logo_data_uri(logo)}" '
            f'alt="Kellogg School of Management"></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="logo-card"><span class="logo-fallback">'
            "Kellogg School of Management</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Add the official Kellogg logo at assets/kellogg_logo.png to display it here."
        )
    st.title("Real Exchange Rate Explorer")
    st.markdown(
        "Monthly IMF data. **S(t)** = units of Country 2 currency per 1 unit of "
        "Country 1 currency; **RER(t) = S(t) × P1(t) / P2(t)**; "
        "**Real Index(t) = 100 × RER(t) / RER\\***."
    )


# --------------------------------------------------------------------------- #
# IMF data access
# --------------------------------------------------------------------------- #
_PERIOD_RE = re.compile(r"^(\d{4})[-_]?M?(\d{1,2})$", re.IGNORECASE)


def _parse_period(value: str) -> pd.Timestamp | pd.NaT:
    """Convert '1976-M01', '1976-01', '197601' to a month-start Timestamp."""
    m = _PERIOD_RE.match(str(value).strip())
    if not m:
        return pd.NaT
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return pd.NaT
    return pd.Timestamp(year=year, month=month, day=1)


def _series_from_csv(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    cols = {c.upper(): c for c in df.columns}
    t_col = cols.get("TIME_PERIOD")
    v_col = cols.get("OBS_VALUE")
    if t_col is None or v_col is None:
        raise ValueError("Unexpected CSV layout from IMF API.")
    out = pd.DataFrame(
        {
            "date": df[t_col].map(_parse_period),
            "value": pd.to_numeric(df[v_col], errors="coerce"),
        }
    ).dropna()
    out = out.drop_duplicates("date").set_index("date")["value"].sort_index()
    return out


def _series_from_json(payload: dict) -> pd.Series:
    """Parse SDMX-JSON (v1 or v2 layout); uses the first series returned."""
    data = payload.get("data", payload)
    structure = None
    if "structures" in data and data["structures"]:
        structure = data["structures"][0]
    elif "structure" in data:
        structure = data["structure"]
    if structure is None:
        raise ValueError("No structure in IMF JSON response.")
    obs_dims = structure["dimensions"]["observation"]
    time_dim = next((d for d in obs_dims if d.get("id") == "TIME_PERIOD"), obs_dims[0])
    time_values = [v.get("id") or v.get("value") for v in time_dim["values"]]

    datasets = data.get("dataSets", [])
    if not datasets or not datasets[0].get("series"):
        return pd.Series(dtype=float)
    series = next(iter(datasets[0]["series"].values()))
    rows = []
    for idx, obs in series.get("observations", {}).items():
        raw = obs[0] if isinstance(obs, list) else obs
        rows.append((_parse_period(time_values[int(idx)]), pd.to_numeric(raw, errors="coerce")))
    s = pd.Series(
        [v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]), dtype=float
    )
    s = s[~s.index.isna()].dropna()
    return s[~s.index.duplicated()].sort_index()


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def fetch_imf_series(flow: str, key: str) -> pd.Series:
    """Fetch one monthly series from the IMF SDMX 3.0 API (CSV first, JSON fallback)."""
    url = f"{IMF_BASE}/data/dataflow/{flow}/+/{key}"
    attempts = [
        ({"Accept": "application/vnd.sdmx.data+csv;version=2.0.0"}, "csv"),
        ({"Accept": "application/vnd.sdmx.data+json;version=2.0.0"}, "json"),
    ]
    last_error = "unknown error"
    for headers, kind in attempts:
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                return pd.Series(dtype=float)  # series does not exist
            resp.raise_for_status()
            s = _series_from_csv(resp.text) if kind == "csv" else _series_from_json(resp.json())
            s = s[s.index >= pd.Timestamp(year=START_YEAR, month=1, day=1)]
            s.name = key
            return s
        except Exception as exc:  # noqa: BLE001 - try next format, report last error
            last_error = f"{type(exc).__name__}: {exc}"
    raise RuntimeError(f"IMF request failed for {key}: {last_error}")


def load_country(code: str) -> tuple[pd.Series, pd.Series]:
    """Return (CPI index, local currency units per USD) for a country code."""
    cpi = fetch_imf_series(CPI_FLOW, f"{code}.CPI._T.IX.M")
    er = fetch_imf_series(ER_FLOW, f"{code}.XDC_USD.PA_RT.M")
    return cpi, er


# --------------------------------------------------------------------------- #
# Calculations
# --------------------------------------------------------------------------- #
def build_dataset(
    cpi1: pd.Series, er1: pd.Series, cpi2: pd.Series, er2: pd.Series
) -> pd.DataFrame:
    """Combine raw series. IMF rates are local currency per USD (XDC_USD).

    S(t) = (C2 per USD) / (C1 per USD) = units of Country 2 currency per Country 1 unit.
    """
    df = pd.concat(
        {"ER1_per_USD": er1, "ER2_per_USD": er2, "P1": cpi1, "P2": cpi2}, axis=1
    ).sort_index()
    df.index.name = "date"
    df["S"] = df["ER2_per_USD"] / df["ER1_per_USD"]
    df["RER"] = df["S"] * df["P1"] / df["P2"]
    return df


def apply_sample(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, float]:
    """Slice to the sample, compute RER* over valid months and the Real Index."""
    sample = df.loc[(df.index >= start) & (df.index <= end)].copy()
    valid = sample[["S", "P1", "P2", "RER"]].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    valid &= sample["RER"] > 0
    sample["valid"] = valid
    rer_star = float(sample.loc[valid, "RER"].mean()) if valid.any() else float("nan")
    sample["RER_star"] = rer_star
    sample["Real_Index"] = np.where(valid, 100.0 * sample["RER"] / rer_star, np.nan)
    return sample, rer_star


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def make_chart(sample: pd.DataFrame, view: str, n1: str, n2: str) -> go.Figure:
    valid = sample[sample["valid"]]
    real_trace = go.Scatter(
        x=valid.index, y=valid["Real_Index"], name="Real Index (RER/RER* × 100)",
        mode="lines", line=dict(color="#4E2A84", width=2.4),
        hovertemplate="%{x|%b %Y}<br>Real Index: %{y:.2f}<extra></extra>",
    )
    nominal_trace = go.Scatter(
        x=valid.index, y=valid["S"], name=f"Nominal S(t) ({n2} per {n1})",
        mode="lines", line=dict(color="#E8A33D", width=2.2),
        hovertemplate="%{x|%b %Y}<br>S: %{y:,.4f}<extra></extra>",
    )
    if view == "Both":
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(real_trace, secondary_y=False)
        fig.add_trace(nominal_trace, secondary_y=True)
        fig.update_yaxes(title_text="Real Index (RER* = 100)", secondary_y=False)
        fig.update_yaxes(title_text=f"S(t): {n2} per 1 {n1}", secondary_y=True, showgrid=False)
    else:
        fig = go.Figure(real_trace if view == "Real" else nominal_trace)
        fig.update_yaxes(
            title_text="Real Index (RER* = 100)" if view == "Real" else f"S(t): {n2} per 1 {n1}"
        )
    if view in ("Real", "Both"):
        fig.add_hline(y=100, line_dash="dot", line_color="#888888", opacity=0.7)
    fig.update_layout(
        template="plotly_white", height=520, hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
def main() -> None:
    apply_theme()
    render_header()

    codes = list(COUNTRIES.keys())
    label = lambda c: f"{COUNTRIES[c]} ({c})"  # noqa: E731

    c1, c2 = st.columns(2)
    code1 = c1.selectbox("Country 1 (base currency)", codes, index=codes.index("USA"), format_func=label)
    code2 = c2.selectbox("Country 2 (quote currency)", codes, index=codes.index("G163"), format_func=label)
    n1, n2 = COUNTRIES[code1], COUNTRIES[code2]

    if code1 == code2:
        st.warning("Please choose two different countries/areas.")
        st.stop()

    with st.spinner("Fetching IMF data..."):
        try:
            cpi1, er1 = load_country(code1)
            cpi2, er2 = load_country(code2)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not retrieve data from the IMF API. {exc}")
            st.stop()

    missing = [
        f"{name}: {what}"
        for name, what, s in [
            (n1, "CPI", cpi1), (n1, "exchange rate", er1),
            (n2, "CPI", cpi2), (n2, "exchange rate", er2),
        ]
        if s.empty
    ]
    if missing:
        st.error("The IMF returned no monthly data for: " + "; ".join(missing) + ".")
        st.stop()

    full = build_dataset(cpi1, er1, cpi2, er2)
    ok = full[["S", "P1", "P2", "RER"]].notna().all(axis=1)
    if not ok.any():
        st.error("The two countries have no overlapping months with complete CPI and exchange-rate data.")
        st.stop()

    first, last = full.index[ok].min(), full.index[ok].max()
    months = list(pd.date_range(first, last, freq="MS"))
    labels = [m.strftime("%b %Y") for m in months]

    st.markdown("#### Sample period")
    start_lbl, end_lbl = st.select_slider(
        "Select start and end months",
        options=labels,
        value=(labels[0], labels[-1]),
        key=f"range_{code1}_{code2}",
    )
    start, end = months[labels.index(start_lbl)], months[labels.index(end_lbl)]

    view = st.radio("Chart view", ["Real", "Nominal", "Both"], horizontal=True, index=2)

    sample, rer_star = apply_sample(full, start, end)
    n_valid = int(sample["valid"].sum())
    if n_valid == 0 or not np.isfinite(rer_star):
        st.error("No valid months in the selected sample. Try a different date range.")
        st.stop()

    m1, m2, m3 = st.columns(3)
    m1.metric("RER* (sample average)", f"{rer_star:,.4f}")
    m2.metric("Valid months", f"{n_valid} of {len(sample)}")
    m3.metric("Latest Real Index", f"{sample.loc[sample['valid'], 'Real_Index'].iloc[-1]:,.1f}")

    st.markdown('<div class="plot-card">', unsafe_allow_html=True)
    st.plotly_chart(make_chart(sample, view, n1, n2), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.caption(
        f"S(t) is quoted as {n2} currency units per one {n1} currency unit. "
        "A Real Index above 100 means Country 1's currency is above its sample-average real "
        "value against Country 2 (i.e., Country 1 goods are relatively expensive). "
        "Months with a missing CPI or exchange rate are excluded from RER* and the chart."
    )

    export = sample.reset_index().rename(
        columns={
            "date": "Date",
            "ER1_per_USD": f"{code1}_currency_per_USD",
            "ER2_per_USD": f"{code2}_currency_per_USD",
            "P1": f"CPI_{code1}",
            "P2": f"CPI_{code2}",
            "S": f"S_{code2}_per_{code1}",
            "RER": "RER",
            "valid": "Valid_month",
            "RER_star": "RER_star",
            "Real_Index": "Real_Index",
        }
    )
    export["Date"] = export["Date"].dt.strftime("%Y-%m")
    csv_bytes = export.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV (selected sample)",
        data=csv_bytes,
        file_name=f"rer_{code1}_{code2}_{start:%Y%m}_{end:%Y%m}.csv",
        mime="text/csv",
    )

    with st.expander("Preview data"):
        st.dataframe(export, use_container_width=True, hide_index=True)

    st.caption("Source: International Monetary Fund (IMF) SDMX 3.0 API. Coverage varies by country.")


if __name__ == "__main__":
    main()
