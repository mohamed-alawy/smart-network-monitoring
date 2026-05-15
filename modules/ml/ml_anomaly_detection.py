"""
ml_anomaly_detection.py - Unsupervised-First ML Anomaly Detection
=================================================================
NO rule-based thresholds. Uses unsupervised models to discover anomalies,
then supervised models learn from unsupervised ensemble labels.

Pipeline:
  1. Isolation Forest (unsupervised)
  2. Local Outlier Factor (unsupervised)
  3. Autoencoder (PyTorch, unsupervised)
  4. Ensemble (majority voting) -> pseudo-labels
  5. XGBoost (supervised, trained on ensemble labels)
  6. Random Forest (supervised, trained on ensemble labels)
  7. Model comparison and best model selection
  8. Apply to full dataset + severity assignment

Usage:
    python ml_anomaly_detection.py
    or
    from ml_anomaly_detection import run_ml_pipeline
"""

import pandas as pd
import numpy as np
import json
import os
import time as t
import joblib
import warnings
from collections import Counter

from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    f1_score, precision_score, recall_score, accuracy_score,
    average_precision_score, confusion_matrix, classification_report,
)

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config import (
    DATA_DIR, ALL_FEATURE_COLS, CONTAMINATION_VALUES,
)
from data_preprocessing import (
    load_and_preprocess_data, generate_anomaly_info,
)

warnings.filterwarnings("ignore")


# ============================================================
# AUTOENCER MODEL (PyTorch)
# ============================================================
class Autoencoder(nn.Module):
    """PyTorch Autoencoder for anomaly detection via reconstruction error."""

    def __init__(self, input_dim: int):
        super().__init__()
        self.enc = nn.Sequential(
            nn.Linear(input_dim, 32), nn.ReLU(), nn.BatchNorm1d(32), nn.Dropout(0.2),
            nn.Linear(32, 16), nn.ReLU(), nn.BatchNorm1d(16), nn.Linear(16, 4),
        )
        self.dec = nn.Sequential(
            nn.Linear(4, 16), nn.ReLU(), nn.BatchNorm1d(16),
            nn.Linear(16, 32), nn.ReLU(), nn.BatchNorm1d(32), nn.Dropout(0.2),
            nn.Linear(32, input_dim),
        )

    def forward(self, x):
        return self.dec(self.enc(x))


# ============================================================
# TRAIN AUTOENCODER
# ============================================================
def train_autoencoder(X_scaled: np.ndarray, epochs: int = 150) -> tuple:
    """
    Train autoencoder on scaled data (unsupervised).
    Returns: (reconstruction_errors, ae_model)
    """
    ae = Autoencoder(X_scaled.shape[1])
    opt = torch.optim.Adam(ae.parameters(), lr=0.001, weight_decay=1e-5)
    sch = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, "min", factor=0.5, patience=10)
    crit = nn.MSELoss()

    X_tensor = torch.FloatTensor(X_scaled)
    loader = DataLoader(TensorDataset(X_tensor), batch_size=64, shuffle=True)

    best_loss, best_state, patience = float("inf"), None, 0
    for ep in range(epochs):
        ae.train()
        for b in loader:
            opt.zero_grad()
            crit(ae(b[0]), b[0]).backward()
            opt.step()
        ae.eval()
        with torch.no_grad():
            loss = crit(ae(X_tensor), X_tensor).item()
        sch.step(loss)
        if loss < best_loss:
            best_loss = loss
            best_state = {k: v.clone() for k, v in ae.state_dict().items()}
            patience = 0
        else:
            patience += 1
        if patience >= 20:
            break

    ae.load_state_dict(best_state)
    ae.eval()
    with torch.no_grad():
        recon_all = ae(X_tensor).numpy()
    errors = np.mean((X_scaled - recon_all) ** 2, axis=1)

    return errors, ae


# ============================================================
# UNSUPERVISED DETECTION
# ============================================================
def run_unsupervised_detection(X_scaled: np.ndarray) -> dict:
    """
    Run all unsupervised models across multiple contamination values.
    Returns: dict with best contamination, ensemble labels, and scores.
    """
    print("\n[Step 2] Running UNSUPERVISED anomaly detection...")

    results = {}

    for cont in CONTAMINATION_VALUES:
        print(f"\n  --- Contamination = {cont*100:.0f}% ---")

        # Isolation Forest
        t0 = t.time()
        iso = IsolationForest(n_estimators=500, contamination=cont, random_state=42, n_jobs=-1)
        iso.fit(X_scaled)
        iso_pred = (iso.predict(X_scaled) == -1).astype(int)
        iso_scores = -iso.decision_function(X_scaled)
        print(f"    Isolation Forest: {iso_pred.sum()} anomalies ({iso_pred.mean()*100:.1f}%) [{t.time()-t0:.1f}s]")

        # LOF
        t0 = t.time()
        lof = LocalOutlierFactor(n_neighbors=20, contamination=cont, novelty=True, n_jobs=-1)
        lof.fit(X_scaled)
        lof_pred = (lof.predict(X_scaled) == -1).astype(int)
        lof_scores = -lof.decision_function(X_scaled)
        print(f"    LOF:              {lof_pred.sum()} anomalies ({lof_pred.mean()*100:.1f}%) [{t.time()-t0:.1f}s]")

        # Autoencoder
        t0 = t.time()
        ae_errors, ae_model = train_autoencoder(X_scaled)
        thresh = np.percentile(ae_errors, (1.0 - cont) * 100)
        ae_pred = (ae_errors > thresh).astype(int)
        print(f"    Autoencoder:      {ae_pred.sum()} anomalies ({ae_pred.mean()*100:.1f}%) [{t.time()-t0:.1f}s]")

        # Ensemble (majority voting, at least 2 of 3)
        ensemble_votes = iso_pred + lof_pred + ae_pred
        ensemble_pred = (ensemble_votes >= 2).astype(int)
        print(f"    Ensemble (>=2/3): {ensemble_pred.sum()} anomalies ({ensemble_pred.mean()*100:.1f}%)")

        results[cont] = {
            "iso_pred": iso_pred, "iso_scores": iso_scores,
            "lof_pred": lof_pred, "lof_scores": lof_scores,
            "ae_pred": ae_pred, "ae_scores": ae_errors,
            "ensemble_pred": ensemble_pred,
            "ae_threshold": thresh,
        }

    # Select best contamination
    print("\n  Selecting best contamination...")
    best_cont = CONTAMINATION_VALUES[0]
    best_score = 0
    for cont in CONTAMINATION_VALUES:
        r = results[cont]
        iso_lof = np.mean(r["iso_pred"] == r["lof_pred"])
        iso_ae = np.mean(r["iso_pred"] == r["ae_pred"])
        avg_agreement = (iso_lof + iso_ae) / 2
        rate = r["ensemble_pred"].mean()
        score = avg_agreement * (1.0 if 0.05 <= rate <= 0.20 else 0.5)
        print(f"    cont={cont*100:.0f}%: rate={rate*100:.1f}%, agreement={avg_agreement*100:.1f}%")
        if score > best_score:
            best_score = score
            best_cont = cont

    print(f"  >>> Selected contamination: {best_cont*100:.0f}%")
    return {
        "best_cont": best_cont,
        "results": results,
        "best_result": results[best_cont],
    }


# ============================================================
# SUPERVISED TRAINING
# ============================================================
def run_supervised_training(X_scaled: np.ndarray, ensemble_labels: np.ndarray,
                            best_result: dict) -> dict:
    """
    Train supervised models (XGBoost, Random Forest) using ensemble pseudo-labels.
    Returns: dict with model info, metrics, and predictions.
    """
    print("\n[Step 3] Training SUPERVISED models on ensemble labels...")

    y = ensemble_labels.copy()
    X = X_scaled.copy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print(f"  Train: {len(X_train)} (anomaly rate: {y_train.mean()*100:.1f}%)")
    print(f"  Test:  {len(X_test)} (anomaly rate: {y_test.mean()*100:.1f}%)")

    # XGBoost
    print("\n  [S1/2] XGBoost Classifier ...")
    t0 = t.time()
    n_pos = int(y_train.sum())
    n_neg = len(y_train) - n_pos
    spw = float(n_neg / n_pos) if n_pos > 0 else 1.0
    spw = max(spw, 1.0)

    import xgboost as xgb
    xgb_model = xgb.XGBClassifier(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, n_jobs=-1, eval_metric="logloss",
        scale_pos_weight=spw,
    )
    xgb_model.fit(X_train, y_train, verbose=False)
    xgb_pred = xgb_model.predict(X_test)
    xgb_scores = xgb_model.predict_proba(X_test)[:, 1]
    print(f"    Done in {t.time()-t0:.2f}s")

    # Random Forest
    print("  [S2/2] Random Forest Classifier ...")
    t0 = t.time()
    rf_model = RandomForestClassifier(
        n_estimators=500, max_depth=8, min_samples_split=10,
        class_weight="balanced", random_state=42, n_jobs=-1,
    )
    rf_model.fit(X_train, y_train)
    rf_pred = rf_model.predict(X_test)
    rf_scores = rf_model.predict_proba(X_test)[:, 1]
    print(f"    Done in {t.time()-t0:.2f}s")

    # Unsupervised model predictions on test set
    _, X_test_idx, _, y_test_orig = train_test_split(
        np.arange(len(X)), y, test_size=0.20, random_state=42, stratify=y
    )

    # Normalize unsupervised scores to [0, 1]
    def normalize(scores):
        mn, mx = scores.min(), scores.max()
        return (scores - mn) / (mx - mn + 1e-8)

    iso_norm = normalize(best_result["iso_scores"])
    lof_norm = normalize(best_result["lof_scores"])
    ae_norm = normalize(best_result["ae_scores"])
    unified_score = (iso_norm + lof_norm + ae_norm) / 3.0

    models_info = {
        "Isolation Forest (unsup)": (best_result["iso_pred"][X_test_idx], iso_norm[X_test_idx]),
        "LOF (unsup)":             (best_result["lof_pred"][X_test_idx], lof_norm[X_test_idx]),
        "Autoencoder (unsup)":     (best_result["ae_pred"][X_test_idx], ae_norm[X_test_idx]),
        "Ensemble (unsup)":        (best_result["ensemble_pred"][X_test_idx], unified_score[X_test_idx]),
        "XGBoost (supervised)":    (xgb_pred, xgb_scores),
        "Random Forest (supervised)": (rf_pred, rf_scores),
    }

    return {
        "models_info": models_info,
        "y_test": y_test,
        "xgb_model": xgb_model,
        "rf_model": rf_model,
        "iso_norm": iso_norm,
        "lof_norm": lof_norm,
        "ae_norm": ae_norm,
        "unified_score": unified_score,
        "X_test_idx": X_test_idx,
    }


# ============================================================
# MODEL COMPARISON
# ============================================================
def compare_models(models_info: dict, y_test: np.ndarray) -> dict:
    """Evaluate all models and return metrics + best model info."""
    print(f"\n[Step 4] Model Comparison ...")
    print(f"{'='*70}")
    print(f"{'Model':<30} {'F1':>8} {'Prec':>8} {'Recall':>8} {'Acc':>8} {'AUC-PR':>8}")
    print("-" * 70)

    metrics = {}
    best_name, best_f1 = "", 0.0

    for name, (pred, sc) in models_info.items():
        f1 = float(f1_score(y_test, pred))
        pr = float(precision_score(y_test, pred, zero_division=0))
        rc = float(recall_score(y_test, pred, zero_division=0))
        ac = float(accuracy_score(y_test, pred))
        try:
            auc = float(average_precision_score(y_test, sc))
        except Exception:
            auc = 0.0
        tn, fp, fn, tp = confusion_matrix(y_test, pred).ravel()

        metrics[name] = {
            "f1_score": round(f1, 4),
            "precision": round(pr, 4),
            "recall": round(rc, 4),
            "accuracy": round(ac, 4),
            "auc_pr": round(auc, 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        }

        tag = " <<<" if f1 > best_f1 else ""
        print(f"{name:<30} {f1:>8.4f} {pr:>8.4f} {rc:>8.4f} {ac:>8.4f} {auc:>8.4f}{tag}")
        if f1 > best_f1:
            best_f1, best_name = f1, name

    print("-" * 70)
    print(f">>> BEST MODEL: {best_name} (F1-Score: {best_f1:.4f})")
    print(f"{'='*70}")

    return {"metrics": metrics, "best_name": best_name, "best_f1": best_f1}


# ============================================================
# SAVE RESULTS
# ============================================================
def save_results(merged_df: pd.DataFrame, comp: dict, sup: dict,
                 ensemble_labels: np.ndarray, best_cont: float,
                 scaler: StandardScaler):
    """Save all output files: model comparison, processed data, anomalies, summary."""
    print("\n[Step 6] Saving output files...")

    best_name = comp["best_name"]
    best_f1 = comp["best_f1"]
    metrics = comp["metrics"]
    models_info = sup["models_info"]

    # Feature importances
    fi_xgb = sorted(
        zip(ALL_FEATURE_COLS, sup["xgb_model"].feature_importances_.tolist()),
        key=lambda x: -x[1],
    )
    fi_rf = sorted(
        zip(ALL_FEATURE_COLS, sup["rf_model"].feature_importances_.tolist()),
        key=lambda x: -x[1],
    )

    # Determine best model predictions for full dataset
    if "XGBoost" in best_name:
        full_pred = sup["xgb_model"].predict(scaler.transform(
            merged_df[ALL_FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(
                merged_df[ALL_FEATURE_COLS].median()
            ).values.astype(np.float64)
        ))
        full_scores = sup["xgb_model"].predict_proba(scaler.transform(
            merged_df[ALL_FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(
                merged_df[ALL_FEATURE_COLS].median()
            ).values.astype(np.float64)
        ))[:, 1]
    elif "Random Forest" in best_name:
        full_pred = sup["rf_model"].predict(scaler.transform(
            merged_df[ALL_FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(
                merged_df[ALL_FEATURE_COLS].median()
            ).values.astype(np.float64)
        ))
        full_scores = sup["rf_model"].predict_proba(scaler.transform(
            merged_df[ALL_FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(
                merged_df[ALL_FEATURE_COLS].median()
            ).values.astype(np.float64)
        ))[:, 1]
    else:
        full_pred = ensemble_labels
        full_scores = sup["unified_score"]

    # Severity assignment based on score percentiles
    anomaly_scores = full_scores[full_pred == 1]
    p80 = float(np.percentile(anomaly_scores, 80)) if len(anomaly_scores) > 0 else 0.8
    p60 = float(np.percentile(anomaly_scores, 60)) if len(anomaly_scores) > 0 else 0.6

    # Build anomaly info for each record
    new_types, new_causes, new_sev, new_count = [], [], [], []
    for i in range(len(merged_df)):
        if full_pred[i] == 1:
            sc = float(full_scores[i])
            row = merged_df.iloc[i]
            severity = "critical" if sc >= p80 else "high" if sc >= p60 else "medium"
            a_types, a_causes = generate_anomaly_info(row, sc, merged_df)
            new_types.append(a_types)
            new_causes.append(a_causes)
            new_sev.append(severity)
            new_count.append(len(a_types))
        else:
            new_types.append([])
            new_causes.append([])
            new_sev.append("low")
            new_count.append(0)

    merged_df["is_anomaly"] = [bool(int(p)) for p in full_pred]
    merged_df["anomaly_types"] = new_types
    merged_df["root_causes"] = new_causes
    merged_df["severity"] = new_sev
    merged_df["anomaly_count"] = new_count
    merged_df["ml_anomaly_score"] = [float(s) for s in full_scores]

    anom_count = int(full_pred.sum())
    norm_count = len(full_pred) - anom_count
    final_rate = anom_count / len(full_pred) * 100
    ensemble_rate = ensemble_labels.mean()

    sev_dist = Counter(new_sev)

    # 1. Model comparison JSON
    comparison = {
        "pipeline_type": "unsupervised-first",
        "unsupervised_contamination": best_cont,
        "ensemble_anomaly_rate": round(float(ensemble_rate) * 100, 2),
        "models_evaluated": list(models_info.keys()),
        "best_model": best_name,
        "best_f1_score": float(best_f1),
        "metrics": metrics,
        "feature_importance_xgb": [{"feature": f, "importance": round(v, 4)} for f, v in fi_xgb],
        "feature_importance_rf": [{"feature": f, "importance": round(v, 4)} for f, v in fi_rf],
        "data_info": {
            "total_records": int(len(merged_df)),
            "features_used": ALL_FEATURE_COLS,
            "unsupervised_models": ["Isolation Forest", "LOF", "Autoencoder"],
            "supervised_models": ["XGBoost", "Random Forest"],
            "final_anomaly_rate": round(final_rate, 2),
        },
    }
    with open(os.path.join(DATA_DIR, "model_comparison.json"), "w") as f:
        json.dump(comparison, f, indent=2)
    print("  [OK] model_comparison.json")

    # 2. Scaler
    joblib.dump(scaler, os.path.join(DATA_DIR, "scaler.pkl"))
    print("  [OK] scaler.pkl")

    # 3. Best model
    if "XGBoost" in best_name:
        sup["xgb_model"].save_model(os.path.join(DATA_DIR, "best_model.json"))
        print("  [OK] best_model.json (XGBoost)")
    else:
        joblib.dump(sup["rf_model"] if "Random" in best_name else sup["xgb_model"],
                    os.path.join(DATA_DIR, "best_model.pkl"))
        print("  [OK] best_model.pkl")

    # 4. Processed data
    export_cols = [
        "measurement_id", "time", "latitude_phone", "longitude_phone",
        "area_name", "district",
        "rsrp_dbm", "rsrq_db", "rssi_dbm", "sinr_db", "pathloss_db",
        "dl_throughput_mbps", "ul_throughput_mbps",
        "operator", "timing_advance", "frequency_khz", "channel_number",
        "pci", "cell_id", "enb_id", "sector_id",
        "height_m", "azimuth_deg", "technology",
        "cell_area_name", "cell_district",
        "latitude_cell", "longitude_cell",
        "is_anomaly", "anomaly_types", "root_causes",
        "severity", "anomaly_count", "ml_anomaly_score",
    ]

    ml_export = merged_df[export_cols].copy()
    ml_export["time"] = ml_export["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    ml_export["cell_area_name"] = ml_export["cell_area_name"].fillna("")
    ml_export["cell_district"] = ml_export["cell_district"].fillna("")
    ml_export["height_m"] = ml_export["height_m"].fillna(0)
    ml_export["azimuth_deg"] = ml_export["azimuth_deg"].fillna(0)
    ml_export["technology"] = ml_export["technology"].fillna("LTE")

    ml_export.to_json(os.path.join(DATA_DIR, "processed_network_data.json"),
                     orient="records", indent=2)
    print("  [OK] processed_network_data.json")

    # 5. Anomalies only
    ml_anom = ml_export[ml_export["is_anomaly"] == True].copy()
    ml_anom.to_json(os.path.join(DATA_DIR, "anomalies_only.json"),
                    orient="records", indent=2)
    print("  [OK] anomalies_only.json")

    # 6. Summary stats
    all_t = []
    for types in ml_anom["anomaly_types"]:
        if isinstance(types, list):
            all_t.extend(types)
    tc = Counter(all_t)

    sev_full = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for k, v in sev_dist.items():
        sev_full[k] = v

    summary = {
        "total_measurements": int(len(ml_export)),
        "anomaly_count": anom_count,
        "normal_count": norm_count,
        "anomaly_rate": round(final_rate, 2),
        "severity_distribution": sev_full,
        "unique_cells": int(ml_export["cell_id"].nunique()),
        "unique_enbs": int(ml_export["enb_id"].nunique()),
        "unique_areas": int(ml_export["area_name"].nunique()),
        "date_range": {
            "start": str(ml_export["time"].min()),
            "end": str(ml_export["time"].max()),
        },
        "detection_model": best_name,
        "model_f1_score": float(best_f1),
        "all_model_f1_scores": {k: v["f1_score"] for k, v in metrics.items()},
        "pipeline_type": "unsupervised-first",
        "unsupervised_contamination": best_cont,
        "ensemble_anomaly_rate": round(float(ensemble_rate) * 100, 2),
        "rsrp_stats": {
            "min": float(ml_export["rsrp_dbm"].min()),
            "max": float(ml_export["rsrp_dbm"].max()),
            "mean": float(round(ml_export["rsrp_dbm"].mean(), 2)),
            "median": float(round(ml_export["rsrp_dbm"].median(), 2)),
        },
        "rsrq_stats": {
            "min": float(ml_export["rsrq_db"].min()),
            "max": float(ml_export["rsrq_db"].max()),
            "mean": float(round(ml_export["rsrq_db"].mean(), 2)),
            "median": float(round(ml_export["rsrq_db"].median(), 2)),
        },
        "sinr_stats": {
            "min": float(ml_export["sinr_db"].min()),
            "max": float(ml_export["sinr_db"].max()),
            "mean": float(round(ml_export["sinr_db"].mean(), 2)),
            "median": float(round(ml_export["sinr_db"].median(), 2)),
        },
        "dl_throughput_stats": {
            "min": float(round(ml_export["dl_throughput_mbps"].min(), 2)),
            "max": float(round(ml_export["dl_throughput_mbps"].max(), 2)),
            "mean": float(round(ml_export["dl_throughput_mbps"].mean(), 2)),
        },
        "ul_throughput_stats": {
            "min": float(round(ml_export["ul_throughput_mbps"].min(), 4)),
            "max": float(round(ml_export["ul_throughput_mbps"].max(), 2)),
            "mean": float(round(ml_export["ul_throughput_mbps"].mean(), 4)),
        },
        "top_anomaly_areas": {
            k: int(v)
            for k, v in ml_export[ml_export["is_anomaly"]]["area_name"]
            .value_counts().head(5).to_dict().items()
        },
        "anomaly_types_distribution": {k: int(v) for k, v in tc.most_common(10)},
    }
    with open(os.path.join(DATA_DIR, "summary_stats.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("  [OK] summary_stats.json")

    return summary


# ============================================================
# MAIN ML PIPELINE
# ============================================================
def run_ml_pipeline():
    """
    Full ML pipeline: preprocess -> unsupervised -> supervised -> compare -> save.
    Returns: summary dict
    """
    print("=" * 70)
    print("  UNSUPERVISED-FIRST  ANOMALY  DETECTION  PIPELINE")
    print("  No Rule-Based Thresholds - Data-Driven Detection")
    print("=" * 70)

    # Step 1: Preprocess
    print("\n[Step 1] Data Preprocessing...")
    merged_df, X_full = load_and_preprocess_data()

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_full)

    # Step 2: Unsupervised detection
    unsup = run_unsupervised_detection(X_scaled)
    best_cont = unsup["best_cont"]
    best_result = unsup["best_result"]
    ensemble_labels = best_result["ensemble_pred"]
    ensemble_rate = ensemble_labels.mean()
    print(f"\n  >>> Ensemble anomaly rate: {ensemble_rate*100:.2f}% ({ensemble_labels.sum()}/{len(ensemble_labels)})")

    # Step 3: Supervised training
    sup = run_supervised_training(X_scaled, ensemble_labels, best_result)

    # Step 4: Model comparison
    comp = compare_models(sup["models_info"], sup["y_test"])

    # Step 5: Print detailed reports
    print("\nDetailed Classification Reports:")
    for name, (pred, _) in sup["models_info"].items():
        print(f"\n--- {name} ---")
        print(classification_report(sup["y_test"], pred, target_names=["Normal", "Anomaly"], digits=4))

    # Feature importance
    print("\nXGBoost Feature Importance:")
    fi = sorted(
        zip(ALL_FEATURE_COLS, sup["xgb_model"].feature_importances_.tolist()),
        key=lambda x: -x[1],
    )
    for feat, val in fi:
        bar = "#" * int(val * 80)
        print(f"  {feat:<35} {val:.4f}  {bar}")

    # Step 6: Save everything
    summary = save_results(merged_df, comp, sup, ensemble_labels, best_cont, scaler)

    # Final report
    print(f"\n{'='*70}")
    print(f"  FINAL RESULTS - UNSUPERVISED-FIRST PIPELINE")
    print(f"{'='*70}")
    print(f"  Best Model            : {comp['best_name']}")
    print(f"  Best F1-Score         : {comp['best_f1']:.4f}")
    print(f"  Anomaly Rate          : {summary['anomaly_rate']:.2f}%")
    print(f"  Total Records         : {summary['total_measurements']}")
    print(f"  Anomaly Records       : {summary['anomaly_count']}")
    print(f"{'='*70}")

    return summary


if __name__ == "__main__":
    run_ml_pipeline()
