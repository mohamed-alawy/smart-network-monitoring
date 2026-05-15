"""
config.py - Project Configuration & Constants
==============================================
Shared settings, file paths, color schemes, 3GPP reference data,
and Vienna area definitions used across all modules.
"""

import os

# ============================================================
# PROJECT SETTINGS
# ============================================================
PROJECT_TITLE = "Telecom Network Anomaly Detection"
PROJECT_SUBTITLE = "AI-Powered Proactive Network Monitoring"
PROJECT_LOCATION = "Vienna, Austria"
PROJECT_TECHNOLOGY = "LTE Network"
PROJECT_PIPELINE = "Unsupervised-First ML Pipeline"

# ============================================================
# PATHS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "upload")
OUTPUT_DIR = os.path.join(BASE_DIR, "data")

RAW_PHONE_CSV = os.path.join(UPLOAD_DIR, "phone_sample.csv")
RAW_CELL_CSV = os.path.join(UPLOAD_DIR, "cell_info_final_lte.csv")

# Auto-create directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
# PLOTLY COLORS & THEME
# ============================================================
PLOTLY_TEMPLATE = "plotly_dark"
COLORS = {
    "bg": "#0f172a",
    "grid": "#1e293b",
    "text": "#94a3b8",
    "blue": "#3b82f6",
    "purple": "#8b5cf6",
    "emerald": "#10b981",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "orange": "#f97316",
    "cyan": "#06b6d4",
    "pink": "#ec4899",
}

SEVERITY_COLORS = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#eab308",
    "low": "#22c55e",
}

MODEL_COLORS = [
    "#3b82f6", "#06b6d4", "#f59e0b", "#a855f7", "#22c55e", "#ef4444",
]

# ============================================================
# 3GPP SIGNAL QUALITY REFERENCE (TS 36.133, TS 36.214)
# ============================================================
SIGNAL_QUALITY_REF = {
    "RSRP": [
        {"range": ">= -80 dBm", "label": "Excellent", "color": "#22c55e"},
        {"range": "-80 to -90 dBm", "label": "Good", "color": "#84cc16"},
        {"range": "-90 to -100 dBm", "label": "Fair", "color": "#eab308"},
        {"range": "-100 to -110 dBm", "label": "Poor", "color": "#f97316"},
        {"range": "< -110 dBm", "label": "Critical", "color": "#ef4444"},
    ],
    "RSRQ": [
        {"range": ">= -8 dB", "label": "Excellent", "color": "#22c55e"},
        {"range": "-8 to -12 dB", "label": "Good", "color": "#84cc16"},
        {"range": "-12 to -15 dB", "label": "Fair", "color": "#eab308"},
        {"range": "-15 to -18 dB", "label": "Poor", "color": "#f97316"},
        {"range": "< -18 dB", "label": "Critical", "color": "#ef4444"},
    ],
    "SINR": [
        {"range": ">= 20 dB", "label": "Excellent", "color": "#22c55e"},
        {"range": "5 to 20 dB", "label": "Good", "color": "#84cc16"},
        {"range": "0 to 5 dB", "label": "Fair", "color": "#eab308"},
        {"range": "-5 to 0 dB", "label": "Poor", "color": "#f97316"},
        {"range": "< -5 dB", "label": "Critical", "color": "#ef4444"},
    ],
}

# ============================================================
# VIENNA AREA DEFINITIONS (for reverse geocoding)
# ============================================================
VIENNA_AREAS = [
    {"name": "Stephansplatz",            "lat": 48.2082, "lon": 16.3738, "district": "1. Innere Stadt"},
    {"name": "Herrengasse",              "lat": 48.2069, "lon": 16.3652, "district": "1. Innere Stadt"},
    {"name": "Graben",                   "lat": 48.2081, "lon": 16.3702, "district": "1. Innere Stadt"},
    {"name": "Kohlmarkt",                "lat": 48.2075, "lon": 16.3679, "district": "1. Innere Stadt"},
    {"name": "Opernring",                "lat": 48.2045, "lon": 16.3690, "district": "1. Innere Stadt"},
    {"name": "Karlsplatz",               "lat": 48.2004, "lon": 16.3716, "district": "1. Innere Stadt"},
    {"name": "Naschmarkt",               "lat": 48.1978, "lon": 16.3647, "district": "6. Mariahilf"},
    {"name": "Museum Quartier",          "lat": 48.2038, "lon": 16.3608, "district": "7. Neubau"},
    {"name": "Mariahilfer Strasse",      "lat": 48.1983, "lon": 16.3475, "district": "6. Mariahilf"},
    {"name": "Rathaus",                  "lat": 48.2095, "lon": 16.3565, "district": "8. Josefstadt"},
    {"name": "Landstrasser Hauptstrasse","lat": 48.1935, "lon": 16.3910, "district": "3. Landstrasse"},
    {"name": "Belvedere",                "lat": 48.1890, "lon": 16.3760, "district": "3. Landstrasse"},
    {"name": "Wieden",                   "lat": 48.1940, "lon": 16.3660, "district": "4. Wieden"},
    {"name": "Margaretenplatz",          "lat": 48.1880, "lon": 16.3620, "district": "5. Margareten"},
    {"name": "Stadtpark",                "lat": 48.2010, "lon": 16.3800, "district": "1. Innere Stadt"},
    {"name": "Schwedenplatz",            "lat": 48.2135, "lon": 16.3765, "district": "1. Innere Stadt"},
    {"name": "Ringstrasse",              "lat": 48.2060, "lon": 16.3630, "district": "1. Innere Stadt"},
    {"name": "Favoritenstrasse",         "lat": 48.1860, "lon": 16.3850, "district": "10. Favoriten"},
    {"name": "Reumannplatz",             "lat": 48.1810, "lon": 16.3780, "district": "10. Favoriten"},
    {"name": "Westbahnhof",              "lat": 48.1958, "lon": 16.3425, "district": "15. Rudolfsheim"},
]

# Map area labels (subset for map annotations)
AREA_CENTERS = {
    "Westbahnhof": (48.195, 16.345),
    "Mariahilfer Strasse": (48.198, 16.35),
    "Naschmarkt": (48.193, 16.365),
    "Karlsplatz": (48.2, 16.37),
}

# ============================================================
# ML PIPELINE SETTINGS
# ============================================================
FEATURE_COLS = [
    "rsrp_dbm", "rsrq_db", "rssi_dbm", "sinr_db", "pathloss_db",
    "dl_throughput_mbps", "ul_throughput_mbps", "timing_advance",
    "frequency_khz", "height_m", "azimuth_deg",
]

ENGINEERED_FEATURE_COLS = [
    "signal_quality_index", "throughput_ratio", "efficiency", "signal_noise_gap",
]

ALL_FEATURE_COLS = FEATURE_COLS + ENGINEERED_FEATURE_COLS

CONTAMINATION_VALUES = [0.03, 0.05, 0.08]

# ============================================================
# DARK THEME CSS (for Streamlit dashboard)
# ============================================================
DARK_CSS = """
<style>
    .stApp { background-color: #060b18; color: #e2e8f0; }
    #MainMenu, footer, header { visibility: hidden; }
    section[data-testid="stSidebar"] { background-color: #0a0f1e; }
    section[data-testid="stSidebar"] .stMarkdown { color: #94a3b8; }

    .stTabs [data-baseweb="tab-list"] {
        gap: 4px; background-color: transparent;
        border-bottom: 1px solid #1e293b; padding: 8px 16px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px; padding: 8px 20px; font-size: 14px;
        font-weight: 500; color: #94a3b8; background-color: transparent;
        border: 1px solid transparent; transition: all 0.2s;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(59, 130, 246, 0.15);
        color: #93c5fd; border-color: rgba(59, 130, 246, 0.3);
    }

    [data-testid="stMetric"] {
        background-color: rgba(15, 23, 42, 0.8);
        border: 1px solid #1e293b; border-radius: 12px; padding: 16px;
    }
    [data-testid="stMetricValue"] { color: #f8fafc; font-size: 24px; font-weight: 700; }
    [data-testid="stMetricLabel"] { color: #64748b; font-size: 12px; }

    .stDataFrame { border-radius: 12px; overflow: hidden; }
    .dataframe { background-color: #0f172a; color: #e2e8f0; }
    .dataframe th { background-color: #1e293b; color: #94a3b8; }
    .dataframe td { border-color: #1e293b; }

    .card {
        background-color: rgba(15, 23, 42, 0.8);
        border: 1px solid #1e293b; border-radius: 12px;
        padding: 20px; margin-bottom: 8px;
    }

    .badge { display: inline-block; padding: 2px 10px; border-radius: 9999px; font-size: 11px; font-weight: 600; }
    .badge-critical { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
    .badge-high { background: rgba(249,115,22,0.15); color: #fb923c; border: 1px solid rgba(249,115,22,0.3); }
    .badge-medium { background: rgba(234,179,8,0.15); color: #facc15; border: 1px solid rgba(234,179,8,0.3); }
    .badge-low { background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }

    .live-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background-color: #10b981; display: inline-block;
        animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    @media (max-width: 768px) { .stTabs [data-baseweb="tab"] { padding: 6px 12px; font-size: 12px; } }
</style>
"""
