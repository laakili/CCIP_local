#!/usr/bin/env python3
"""
Importe les traitements déjà réalisés (TP1, TP2, TP3) dans la plateforme
pour qu'ils apparaissent dans l'historique
"""

import os, sys, json, datetime, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.pipeline import Job
from core.config   import RESULTS_DIR

OUTPUTS = "/Users/mac/Documents/Projet/CRTS/innodation/outputs"

def import_tp2():
    """Importe le résultat TP2 (image unique 03/02/2026)"""
    job_id = "tp2_20260203"
    outdir = os.path.join(RESULTS_DIR, job_id)
    os.makedirs(outdir, exist_ok=True)

    mask_src = f"{OUTPUTS}/TP2/mask_water_20260203.tif"
    mask_dst = os.path.join(outdir, "mask_water.tif")
    if os.path.exists(mask_src) and not os.path.exists(mask_dst):
        os.symlink(mask_src, mask_dst)

    zi_src  = f"{OUTPUTS}/TP3/ZI_20260203_stats.shp"
    csv_src = f"{OUTPUTS}/TP3/ZI_stats_communes_L4.csv"
    csv_dst = os.path.join(outdir, "statistiques_communes.csv")
    if os.path.exists(csv_src) and not os.path.exists(csv_dst):
        shutil.copy2(csv_src, csv_dst)

    prov_dst = os.path.join(outdir, "provinces")
    prov_src = f"{OUTPUTS}/TP3/Provinces_stats"
    if os.path.exists(prov_src) and not os.path.exists(prov_dst):
        os.symlink(prov_src, prov_dst)

    # Lire les stats pour le rapport
    rows, total = [], 0.0
    if os.path.exists(csv_dst):
        import csv
        with open(csv_dst) as f:
            for row in csv.DictReader(f):
                if row.get("Commune") and row.get("Surface_ZI_ha"):
                    try:
                        area = float(row["Surface_ZI_ha"])
                        rows.append(row); total += area
                    except: pass
    rows.sort(key=lambda r: -float(r.get("Surface_ZI_ha", 0)))

    state = {
        "id": job_id,
        "status": "done",
        "progress": 100,
        "created": "2026-03-30T16:22:00",
        "finished": "2026-03-30T22:11:00",
        "params": {
            "image_after": "/Users/mac/Downloads/S1A_IW_GRDH_1SDV_20260203T062746_20260203T062811_063051_07E997_9846.zip",
            "polarisation": "VH",
            "pixel_spacing": 10.0,
            "dem": "SRTM 1Sec HGT",
            "seuil_db": -26.0,
            "area_min_ha": 0.5,
            "epsg": 32629,
            "aoi": {"lon_min": -6.8, "lat_min": 33.5, "lon_max": -4.8, "lat_max": 35.8}
        },
        "results": {
            "mask_water":     mask_dst,
            "zones_inondees": zi_src,
            "stats_csv":      csv_dst,
            "provinces_dir":  prov_dst,
            "rapport":        os.path.join(outdir, "rapport.html"),
        },
        "logs": [
            {"ts":"16:22","level":"INFO","msg":"=== DÉMARRAGE DU PIPELINE INONDATION ==="},
            {"ts":"16:22","level":"INFO","msg":"Mode IMAGE UNIQUE détecté → TP2 (seuillage VH)"},
            {"ts":"16:23","level":"SNAP","msg":"Apply Orbit File → Thermal Noise Removal → Calibration"},
            {"ts":"16:28","level":"SNAP","msg":"Speckle Filter (Refined Lee 7x7) → Terrain Correction SRTM 1Sec"},
            {"ts":"16:33","level":"SNAP","msg":"LinearToFromdB → BandMaths seuil -26 dB → 100% done."},
            {"ts":"16:36","level":"QGIS","msg":"[A] Lissage gaussien sigma=2"},
            {"ts":"16:36","level":"QGIS","msg":"[B] Seuil Natural Breaks: 0.4759"},
            {"ts":"16:37","level":"QGIS","msg":"[C] Polygones: 1733 conservés, 3011 supprimés (<0.5 ha)"},
            {"ts":"22:04","level":"QGIS","msg":"  Surface totale: 22,175.73 ha | 95 communes | 8 provinces"},
            {"ts":"22:11","level":"INFO","msg":"=== PIPELINE TERMINÉ AVEC SUCCÈS ==="},
        ]
    }

    # Générer le rapport HTML
    from core.pipeline import FloodPipeline
    job = Job(job_id, state["params"])
    job.results = state["results"]
    job.logs    = state["logs"]
    fp = FloodPipeline(job)
    html = fp._build_report_html(rows, total)
    with open(os.path.join(outdir, "rapport.html"), "w", encoding="utf-8") as f:
        f.write(html)

    with open(os.path.join(outdir, "state.json"), "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"  ✓ TP2 importé: {job_id}")


def import_tp1():
    """Importe le résultat TP1 (avant/après)"""
    job_id = "tp1_avant_apres"
    outdir = os.path.join(RESULTS_DIR, job_id)
    os.makedirs(outdir, exist_ok=True)

    csv_src = f"{OUTPUTS}/TP3/ZI_stats_communes_L4.csv"
    csv_dst = os.path.join(outdir, "statistiques_communes.csv")
    if os.path.exists(csv_src) and not os.path.exists(csv_dst):
        shutil.copy2(csv_src, csv_dst)

    rows, total = [], 0.0
    if os.path.exists(csv_dst):
        import csv
        with open(csv_dst) as f:
            for row in csv.DictReader(f):
                if row.get("Commune") and row.get("Surface_ZI_ha"):
                    try:
                        area = float(row["Surface_ZI_ha"])
                        rows.append(row); total += area
                    except: pass
    rows.sort(key=lambda r: -float(r.get("Surface_ZI_ha", 0)))

    before_db = f"{OUTPUTS}/TP1/before_20260128_dB.tif"
    after_db  = f"{OUTPUTS}/TP1/after_20260203_dB.tif"
    rgb_tif   = f"{OUTPUTS}/TP1/RGB_composite_inondation.tif"
    mask_tif  = f"{OUTPUTS}/TP1/water_mask_diff_method.tif"
    diff_tif  = f"{OUTPUTS}/TP1/amplitude_diff_dB.tif"

    state = {
        "id": job_id,
        "status": "done",
        "progress": 100,
        "created": "2026-03-30T16:20:00",
        "finished": "2026-03-30T16:38:00",
        "params": {
            "image_after":  "/Users/mac/Downloads/S1A_IW_GRDH_1SDV_20260203T062746_20260203T062811_063051_07E997_9846.zip",
            "image_before": "/Users/mac/Downloads/S1C_IW_GRDH_1SDV_20260128T062655_20260128T062720_006100_00C3CC_346B.SAFE.zip",
            "polarisation": "VH",
            "pixel_spacing": 10.0,
            "dem": "SRTM 1Sec HGT",
            "seuil_db": -26.0,
            "area_min_ha": 0.5,
            "epsg": 32629,
            "aoi": {"lon_min": -6.8, "lat_min": 33.5, "lon_max": -4.8, "lat_max": 35.8}
        },
        "results": {
            "before_db":     before_db,
            "after_db":      after_db,
            "diff_db":       diff_tif,
            "rgb":           rgb_tif,
            "mask_water":    mask_tif,
            "stats_csv":     csv_dst,
            "rapport":       os.path.join(outdir, "rapport.html"),
        },
        "logs": [
            {"ts":"16:20","level":"INFO","msg":"=== DÉMARRAGE DU PIPELINE INONDATION ==="},
            {"ts":"16:20","level":"INFO","msg":"Mode AVANT/APRÈS détecté → TP1 (différence d'amplitude)"},
            {"ts":"16:20","level":"SNAP","msg":"TP1-BEFORE: Apply Orbit → TNR → Calibration → Speckle → TC → dB"},
            {"ts":"16:24","level":"SNAP","msg":"TP1-BEFORE: 100% done. → before_20260128_dB.tif"},
            {"ts":"16:25","level":"SNAP","msg":"TP1-AFTER:  Apply Orbit → TNR → Calibration → Speckle → TC → dB"},
            {"ts":"16:33","level":"SNAP","msg":"TP1-AFTER:  100% done. → after_20260203_dB.tif"},
            {"ts":"16:38","level":"QGIS","msg":"Coregistration + Différence d'amplitude calculée"},
            {"ts":"16:38","level":"QGIS","msg":"Taille images: 18261 x 20224 — Avant dB: -44.75/+13.88, Après: -56.75/+13.87"},
            {"ts":"16:38","level":"QGIS","msg":"Différence — Min: -42.63, Max: 56.75, Moy: +3.53 dB"},
            {"ts":"16:38","level":"QGIS","msg":"Pixels inondés (diff > 3 dB): 107,479,323 / 369,310,464 (29.1%)"},
            {"ts":"16:38","level":"QGIS","msg":"RGB composite sauvegardé (R=avant, G=B=après)"},
            {"ts":"16:38","level":"INFO","msg":"=== PIPELINE TERMINÉ AVEC SUCCÈS ==="},
        ]
    }

    from core.pipeline import FloodPipeline
    job = Job(job_id, state["params"])
    job.results = state["results"]
    job.logs    = state["logs"]
    fp = FloodPipeline(job)
    html = fp._build_report_html(rows, total)
    with open(os.path.join(outdir, "rapport.html"), "w", encoding="utf-8") as f:
        f.write(html)

    with open(os.path.join(outdir, "state.json"), "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"  ✓ TP1 importé: {job_id}")


if __name__ == "__main__":
    print("Importation des résultats existants dans la plateforme...")
    import_tp2()
    import_tp1()
    print("Import terminé.")
