"""
data_preprocessing.py - Data Loading & Preprocessing Pipeline
=============================================================
Handles raw data loading, cleaning, merging phone + cell data,
reverse geocoding to Vienna areas, and feature engineering.

Usage:
    python data_preprocessing.py
    or
    from data_preprocessing import load_and_preprocess_data
"""

import pandas as pd
import numpy as np
import json
import math
from collections import Counter

from config import (
    RAW_PHONE_CSV, RAW_CELL_CSV, DATA_DIR,
    VIENNA_AREAS, FEATURE_COLS, ENGINEERED_FEATURE_COLS, ALL_FEATURE_COLS,
)


def get_nearest_area(lat: float, lon: float) -> tuple:
    """
    Find the nearest Vienna area to given coordinates.
    Returns: (area_name, district)
    """
    min_dist = float("inf")
    nearest = VIENNA_AREAS[0]
    for area in VIENNA_AREAS:
        dist = math.sqrt((lat - area["lat"]) ** 2 + (lon - area["lon"]) ** 2)
        if dist < min_dist:
            min_dist = dist
            nearest = area
    return nearest["name"], nearest["district"]


def load_raw_data():
    """Load raw CSV files and return phone_df and cell_df."""
    print("[1/5] Loading raw datasets...")
    phone_df = pd.read_csv(RAW_PHONE_CSV)
    cell_df = pd.read_csv(RAW_CELL_CSV)
    print(f"  Phone records: {len(phone_df)}")
    print(f"  Cell records:  {len(cell_df)}")
    return phone_df, cell_df


def clean_data(phone_df: pd.DataFrame) -> pd.DataFrame:
    """Clean phone measurement data: remove nulls, fix types."""
    print("[2/5] Cleaning data...")
    phone_df = phone_df.dropna(
        subset=["latitude", "longitude", "rsrp_dbm", "rsrq_db", "sinr_db"]
    )
    phone_df["time"] = pd.to_datetime(phone_df["time"], errors="coerce")
    phone_df = phone_df.dropna(subset=["time"])

    for col in ["timing_advance", "dl_throughput_mbps", "ul_throughput_mbps"]:
        if col in phone_df.columns:
            phone_df[col] = phone_df[col].fillna(phone_df[col].median())

    print(f"  After cleaning: {len(phone_df)} phone records")
    return phone_df


def merge_datasets(phone_df: pd.DataFrame, cell_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge phone measurements with cell tower information.
    Handles unmatched records via eNB-level fallback lookup.
    """
    print("[3/5] Merging phone and cell data...")

    merged_df = phone_df.merge(
        cell_df[
            [
                "enb_id", "sector_id", "cell_id", "pci",
                "latitude", "longitude", "height_m", "azimuth_deg",
                "channel_number", "technology",
            ]
        ],
        on=["cell_id", "enb_id", "sector_id", "pci", "channel_number"],
        how="left",
        suffixes=("_phone", "_cell"),
    )

    # Back-fill unmatched rows via eNB lookup
    unmatched = merged_df[merged_df["latitude_cell"].isna()]
    if len(unmatched) > 0:
        cell_lookup = (
            cell_df.groupby("enb_id")
            .agg(
                latitude=("latitude", "first"),
                longitude=("longitude", "first"),
                height_m=("height_m", "first"),
                azimuth_deg=("azimuth_deg", "first"),
                technology=("technology", "first"),
            )
            .reset_index()
        )
        for idx in unmatched.index:
            enb = unmatched.loc[idx, "enb_id"]
            match = cell_lookup[cell_lookup["enb_id"] == enb]
            if len(match) > 0:
                merged_df.loc[idx, "latitude_cell"] = match.iloc[0]["latitude"]
                merged_df.loc[idx, "longitude_cell"] = match.iloc[0]["longitude"]
                merged_df.loc[idx, "height_m"] = match.iloc[0]["height_m"]
                merged_df.loc[idx, "azimuth_deg"] = match.iloc[0]["azimuth_deg"]
                merged_df.loc[idx, "technology"] = match.iloc[0]["technology"]

    matched_count = merged_df["latitude_cell"].notna().sum()
    print(f"  Matched records: {matched_count}/{len(merged_df)}")
    return merged_df


def reverse_geocode(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign Vienna area names and districts based on GPS coordinates.
    Uses nearest-neighbor matching to predefined area centers.
    """
    print("[4/5] Reverse geocoding (Vienna areas)...")

    phone_areas = merged_df.apply(
        lambda row: get_nearest_area(row["latitude_phone"], row["longitude_phone"]),
        axis=1,
    )
    merged_df["area_name"] = phone_areas.apply(lambda x: x[0])
    merged_df["district"] = phone_areas.apply(lambda x: x[1])

    cell_areas = merged_df.dropna(subset=["latitude_cell", "longitude_cell"]).apply(
        lambda row: get_nearest_area(row["latitude_cell"], row["longitude_cell"]),
        axis=1,
    )
    merged_df.loc[cell_areas.index, "cell_area_name"] = cell_areas.apply(lambda x: x[0])
    merged_df.loc[cell_areas.index, "cell_district"] = cell_areas.apply(lambda x: x[1])

    print(f"  Areas assigned: {merged_df['area_name'].nunique()} unique areas")
    return merged_df


def engineer_features(merged_df: pd.DataFrame) -> tuple:
    """
    Create derived features for ML models:
    - signal_quality_index: weighted composite of RSRP, RSRQ, SINR
    - throughput_ratio: DL/UL throughput ratio
    - efficiency: DL throughput per channel number
    - signal_noise_gap: RSRP minus RSSI

    Returns: (merged_df, X_features)
    """
    print("[5/5] Feature engineering...")

    merged_df["signal_quality_index"] = (
        (merged_df["rsrp_dbm"] + 120) / 60 * 0.4
        + (merged_df["rsrq_db"] + 30) / 30 * 0.3
        + (merged_df["sinr_db"] + 10) / 40 * 0.3
    )
    merged_df["throughput_ratio"] = merged_df["dl_throughput_mbps"] / (
        merged_df["ul_throughput_mbps"] + 0.001
    )
    merged_df["efficiency"] = merged_df["dl_throughput_mbps"] / (
        merged_df["channel_number"] + 1
    )
    merged_df["signal_noise_gap"] = merged_df["rsrp_dbm"] - merged_df["rssi_dbm"]

    X_full = merged_df[ALL_FEATURE_COLS].copy().replace([np.inf, -np.inf], np.nan)
    X_full = X_full.fillna(X_full.median()).astype(np.float64)

    print(f"  Features ({len(ALL_FEATURE_COLS)}): {ALL_FEATURE_COLS}")
    print(f"  Records: {len(X_full)}")

    # Data distribution stats
    print(f"\n  Data Distribution:")
    print(f"    RSRP: mean={merged_df['rsrp_dbm'].mean():.1f}, std={merged_df['rsrp_dbm'].std():.1f}, "
          f"min={merged_df['rsrp_dbm'].min():.1f}, max={merged_df['rsrp_dbm'].max():.1f}")
    print(f"    RSRQ: mean={merged_df['rsrq_db'].mean():.1f}, std={merged_df['rsrq_db'].std():.1f}, "
          f"min={merged_df['rsrq_db'].min():.1f}, max={merged_df['rsrq_db'].max():.1f}")
    print(f"    SINR: mean={merged_df['sinr_db'].mean():.1f}, std={merged_df['sinr_db'].std():.1f}, "
          f"min={merged_df['sinr_db'].min():.1f}, max={merged_df['sinr_db'].max():.1f}")

    return merged_df, X_full


def generate_anomaly_info(row: pd.Series, score: float,
                          merged_df: pd.DataFrame) -> tuple:
    """
    Generate anomaly types and root causes based on actual data values.
    Uses Z-score analysis relative to data distribution (NOT rule-based thresholds).
    Returns: (anomaly_types: list, root_causes: list)
    """
    anomalies = []
    root_causes = []

    rsrp = row.get("rsrp_dbm", 0)
    rsrq = row.get("rsrq_db", 0)
    sinr = row.get("sinr_db", 0)
    dl_tp = row.get("dl_throughput_mbps", 0)
    ul_tp = row.get("ul_throughput_mbps", 0)
    pathloss = row.get("pathloss_db", 0)
    sqi = row.get("signal_quality_index", 0.5)

    # Z-scores relative to data distribution
    rsrp_z = (rsrp - merged_df["rsrp_dbm"].mean()) / (merged_df["rsrp_dbm"].std() + 1e-8)
    rsrq_z = (rsrq - merged_df["rsrq_db"].mean()) / (merged_df["rsrq_db"].std() + 1e-8)
    sinr_z = (sinr - merged_df["sinr_db"].mean()) / (merged_df["sinr_db"].std() + 1e-8)

    # Detect anomalies (beyond 1.5 std from mean)
    if rsrp_z < -1.5:
        anomalies.append(f"RSRP deviation detected ({rsrp:.1f} dBm)")
        if rsrp < -110:
            root_causes.append("Extreme signal weakness - possible coverage hole or hardware fault")
        elif rsrp < -100:
            root_causes.append("Weak signal - building penetration loss or cell edge")
        else:
            root_causes.append("Below-average RSRP - possible obstruction or distance")

    if rsrq_z < -1.5:
        anomalies.append(f"RSRQ deviation detected ({rsrq:.1f} dB)")
        if rsrq < -18:
            root_causes.append("Severe interference - PCI conflict or external RF source")
        elif rsrq < -15:
            root_causes.append("Moderate interference - co-channel or adjacent channel")
        else:
            root_causes.append("Below-average RSRQ - mild interference present")

    if sinr_z < -1.5:
        anomalies.append(f"SINR deviation detected ({sinr:.1f} dB)")
        if sinr < -3:
            root_causes.append("Very high noise floor - signal barely usable")
        elif sinr < 0:
            root_causes.append("High noise floor - interference dominated environment")
        else:
            root_causes.append("Elevated noise - possible external interference")

    # Throughput anomalies
    dl_z = (dl_tp - merged_df["dl_throughput_mbps"].mean()) / (merged_df["dl_throughput_mbps"].std() + 1e-8)
    ul_z = (ul_tp - merged_df["ul_throughput_mbps"].mean()) / (merged_df["ul_throughput_mbps"].std() + 1e-8)

    if dl_z < -1.5 and rsrp_z > -1.0:
        anomalies.append(f"DL throughput anomaly ({dl_tp:.1f} Mbps despite good signal)")
        root_causes.append("Backhaul congestion or scheduling issue")

    if ul_z < -1.5:
        anomalies.append(f"UL throughput deviation ({ul_tp:.2f} Mbps)")
        root_causes.append("Uplink interference or power control issue")

    # Path loss
    pl_z = (pathloss - merged_df["pathloss_db"].mean()) / (merged_df["pathloss_db"].std() + 1e-8)
    if pl_z > 1.5:
        anomalies.append(f"High path loss ({pathloss:.0f} dB)")
        root_causes.append("Excessive propagation loss - indoor or behind obstacle")

    # Signal Quality Index
    if sqi < 0.35:
        anomalies.append("Composite signal quality degradation")
        root_causes.append("Overall signal quality index below acceptable")

    # Multi-metric degradation
    degraded_count = sum([1 for z in [rsrp_z, rsrq_z, sinr_z] if z < -1.0])
    if degraded_count >= 2:
        anomalies.append(f"Multi-metric degradation ({degraded_count} KPIs below normal)")
        root_causes.append("Combined signal degradation - possible coverage hole or handover issue")

    # If ML detected anomaly but no specific metric trigger
    if len(anomalies) == 0:
        anomalies.append("ML-detected statistical anomaly")
        root_causes.append("Pattern deviation detected by AI - subtle metric combination unusual")

    return anomalies, root_causes


def load_and_preprocess_data() -> tuple:
    """
    Full preprocessing pipeline.
    Returns: (merged_df, X_features)
    """
    phone_df, cell_df = load_raw_data()
    phone_df = clean_data(phone_df)
    merged_df = merge_datasets(phone_df, cell_df)
    merged_df = reverse_geocode(merged_df)
    merged_df, X_full = engineer_features(merged_df)
    return merged_df, X_full


# ============================================================
# STANDALONE EXECUTION
# ============================================================
if __name__ == "__main__":
    merged_df, X_full = load_and_preprocess_data()
    print(f"\nPreprocessing complete!")
    print(f"  Total records: {len(merged_df)}")
    print(f"  Feature columns: {len(ALL_FEATURE_COLS)}")
    print(f"  Areas covered: {merged_df['area_name'].nunique()}")
