"""
Plateforme Gestion de Crise Inondation — Pipeline principal
Orchestre TP1 + TP2 + TP3 en séquence ou en parallèle
"""

import os, sys, json, time, subprocess, threading, datetime, shutil
from pathlib import Path
from .config import (SNAP_GPT, PYTHON_QGIS, GDAL_BIN, GDAL_POLYGONIZE, QGIS_ENV,
                     DEFAULT_PARAMS, RESULTS_DIR, GRAPHS_DIR, GADM_DEFAULT)

# En Docker (mémoire limitée) : USE_BLOCKS=1 → traitement par blocs
# En local (Mac, RAM suffisante) : USE_BLOCKS=0 → ReadAsArray rapide
USE_BLOCKS = os.environ.get("USE_BLOCKS", "0") == "1"

class _CancelledError(Exception):
    pass

class Job:
    """Représente un job de traitement avec son état et ses logs"""
    def __init__(self, job_id, params):
        self.id        = job_id
        self.params    = params
        self.status    = "pending"   # pending → running → done / error
        self.progress  = 0
        self.logs      = []
        self.results   = {}
        self.created   = datetime.datetime.now().isoformat()
        self.finished  = None
        self.outdir    = os.path.join(RESULTS_DIR, job_id)
        os.makedirs(self.outdir, exist_ok=True)

    def log(self, msg, level="INFO"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {"ts": ts, "level": level, "msg": msg}
        self.logs.append(entry)
        print(f"[{ts}][{self.id}][{level}] {msg}")
        self._save_state()

    def set_progress(self, pct, step=""):
        self.progress = pct
        if step:
            self.log(f"({pct}%) {step}")
        self._save_state()

    def _save_state(self):
        state = {
            "id":       self.id,
            "status":   self.status,
            "progress": self.progress,
            "logs":     self.logs[-100:],
            "results":  self.results,
            "created":  self.created,
            "finished": self.finished,
            "params":   {k: v for k, v in self.params.items() if k != "files"},
        }
        with open(os.path.join(self.outdir, "state.json"), "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


class FloodPipeline:
    """Pipeline complet : Prétraitement SNAP → Masque eau → Vectorisation → Statistiques"""

    def __init__(self, job: Job):
        self.job    = job
        self.p      = {**DEFAULT_PARAMS, **job.params}
        self.outdir = job.outdir

    # ------------------------------------------------------------------
    # ENTRÉE PRINCIPALE
    # ------------------------------------------------------------------
    def run(self):
        job = self.job
        job.status = "running"
        job.log("=== DÉMARRAGE DU PIPELINE INONDATION ===")

        try:
            # TP1 / TP2 : prétraitement SNAP
            if self.p.get("image_before") and self.p.get("image_after"):
                job.log("Mode AVANT/APRÈS détecté → TP1 (différence d'amplitude)")
                self._run_tp1()
            elif self.p.get("image_after"):
                job.log("Mode IMAGE UNIQUE détecté → TP2 (seuillage VH)")
                self._run_tp2()
            else:
                raise ValueError("Au moins une image Sentinel-1 est requise")

            self._check_cancelled()

            # TP3 : vectorisation et statistiques
            self._run_tp3()

            self._check_cancelled()

            # Rapport final
            self._generate_report()

            job.status   = "done"
            job.progress = 100
            job.finished = datetime.datetime.now().isoformat()
            job.log("=== PIPELINE TERMINÉ AVEC SUCCÈS ===")

        except _CancelledError:
            job.log("Pipeline interrompu par l'utilisateur", "WARN")
        except Exception as e:
            job.status = "error"
            job.log(f"ERREUR FATALE: {e}", "ERROR")
            import traceback
            job.log(traceback.format_exc(), "ERROR")
        finally:
            job._save_state()

    # ------------------------------------------------------------------
    # TP2 — WORKFLOW SNAP IMAGE UNIQUE (Feb 2026 style)
    # ------------------------------------------------------------------
    def _run_tp2(self):
        job = self.job
        job.log("── TP2: Workflow SNAP image unique ──")

        p        = self.p
        img      = p["image_after"]
        aoi      = p.get("aoi", DEFAULT_PARAMS["aoi"])
        pol      = p.get("polarisation", "VH")
        px       = p.get("pixel_spacing", 10.0)
        dem      = p.get("dem", "SRTM 1Sec HGT")
        epsg     = p.get("epsg", 32629)
        after_db = os.path.join(self.outdir, "after_dB.tif")
        out_mask = os.path.join(self.outdir, "mask_water.tif")

        # SNAP → raster dB (même graph que TP1, sans BandMaths)
        job.set_progress(5, "Génération du graph SNAP")
        graph_xml = self._write_snap_graph_preprocess(img, aoi, pol, px, dem, epsg, after_db)

        job.set_progress(10, "Exécution SNAP (Apply Orbit → TNR → Calibration → Speckle → TC → dB)")
        success = self._run_snap_graph(graph_xml, label="TP2-SNAP")
        if not success or not os.path.exists(after_db):
            raise RuntimeError("SNAP TP2 a échoué — vérifier les logs")

        # Seuillage automatique K-means en Python
        job.set_progress(40, "Détection automatique du seuil eau (K-means)")
        mask_script = self._write_tp2_mask_script(after_db, out_mask)
        ok = self._run_qgis_script(mask_script, label="TP2-MASK")
        if not ok or not os.path.exists(out_mask):
            raise RuntimeError("Seuillage TP2 a échoué")

        job.results.update({"after_db": after_db, "mask_water": out_mask})
        job.set_progress(45, "Masque eau généré (seuil automatique)")

    # ------------------------------------------------------------------
    # TP1 — WORKFLOW SNAP AVANT/APRÈS (Différence d'amplitude)
    # ------------------------------------------------------------------
    def _run_tp1(self):
        job = self.job
        job.log("── TP1: Workflow SNAP avant/après ──")

        p       = self.p
        aoi     = p.get("aoi", DEFAULT_PARAMS["aoi"])
        pol     = p.get("polarisation", "VH")
        px      = p.get("pixel_spacing", 10.0)
        dem     = p.get("dem", "SRTM 1Sec HGT")
        epsg    = p.get("epsg", 32629)

        before_db  = os.path.join(self.outdir, "before_dB.tif")
        after_db   = os.path.join(self.outdir, "after_dB.tif")
        diff_tif   = os.path.join(self.outdir, "amplitude_diff_dB.tif")
        rgb_tif    = os.path.join(self.outdir, "RGB_composite.tif")
        out_mask   = os.path.join(self.outdir, "mask_water.tif")

        # Traitement image AVANT
        job.set_progress(5, "Traitement image AVANT (SNAP)")
        g_before = self._write_snap_graph_preprocess(p["image_before"], aoi, pol, px, dem, epsg, before_db)
        ok_before = self._run_snap_graph(g_before, label="TP1-BEFORE")
        if not ok_before or not os.path.exists(before_db):
            raise RuntimeError("SNAP TP1-BEFORE a échoué — vérifier les logs SNAP ci-dessus")

        # Traitement image APRÈS
        job.set_progress(25, "Traitement image APRÈS (SNAP)")
        g_after  = self._write_snap_graph_preprocess(p["image_after"],  aoi, pol, px, dem, epsg, after_db)
        ok_after = self._run_snap_graph(g_after, label="TP1-AFTER")
        if not ok_after or not os.path.exists(after_db):
            raise RuntimeError("SNAP TP1-AFTER a échoué — vérifier les logs SNAP ci-dessus")

        # Calcul diff + RGB + masque (script QGIS)
        job.set_progress(45, "Calcul différence d'amplitude + RGB + masque eau")
        diff_script = self._write_diff_script(before_db, after_db, diff_tif, rgb_tif, out_mask)
        self._run_qgis_script(diff_script, label="TP1-DIFF")

        job.results.update({
            "before_db":  before_db,
            "after_db":   after_db,
            "diff_db":    diff_tif,
            "rgb":        rgb_tif,
            "mask_water": out_mask,
        })
        job.set_progress(50, "Composition RGB générée — zones inondées en rouge")

    # ------------------------------------------------------------------
    # TP3 — VECTORISATION + STATS (QGIS/GDAL)
    # ------------------------------------------------------------------
    def _run_tp3(self):
        job = self.job
        job.log("── TP3: Vectorisation + Statistiques ──")

        mask_water  = job.results.get("mask_water")
        if not mask_water or not os.path.exists(mask_water):
            raise RuntimeError(f"Masque eau introuvable: {mask_water}")

        zi_shp      = os.path.join(self.outdir, "ZI_inondation.shp")
        stats_csv   = os.path.join(self.outdir, "statistiques_communes.csv")
        prov_dir    = os.path.join(self.outdir, "provinces")
        os.makedirs(prov_dir, exist_ok=True)

        # Communes GADM
        communes    = self.p.get("communes_shp", self._find_gadm())

        job.set_progress(55, "Lissage + reclassification du masque")
        tp3_script = self._write_tp3_script(mask_water, zi_shp, communes, stats_csv, prov_dir)
        self._run_qgis_script(tp3_script, label="TP3")

        job.results.update({
            "zones_inondees": zi_shp,
            "stats_csv":      stats_csv,
            "provinces_dir":  prov_dir,
        })
        job.set_progress(90, "Vectorisation et statistiques terminées")

    # ------------------------------------------------------------------
    # GÉNÉRATEUR RAPPORT HTML
    # ------------------------------------------------------------------
    def _generate_report(self):
        job = self.job
        job.set_progress(95, "Génération du rapport HTML")

        # Lire les stats
        stats_csv = job.results.get("stats_csv", "")
        rows = []
        total = 0.0
        if os.path.exists(stats_csv):
            with open(stats_csv) as f:
                import csv
                for row in csv.DictReader(f):
                    if row.get("Commune") and row.get("Surface_ZI_ha"):
                        try:
                            area = float(row["Surface_ZI_ha"])
                            rows.append(row)
                            total += area
                        except:
                            pass

        # Trier par surface décroissante
        rows.sort(key=lambda r: -float(r.get("Surface_ZI_ha", 0)))

        report_path = os.path.join(self.outdir, "rapport.html")
        html = self._build_report_html(rows, total)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        job.results["rapport"] = report_path
        job.log(f"Rapport HTML: {report_path}")

    # ------------------------------------------------------------------
    # GÉNÉRATEUR XML SNAP — TP2 (image unique GRD)
    # ------------------------------------------------------------------
    def _write_snap_graph_tp2(self, img, aoi, pol, px, dem, seuil_db, epsg, out_mask):
        path = os.path.join(self.outdir, "snap_graph_tp2.xml")
        expr = f"Sigma0_{pol}_db &lt; {seuil_db} ? 1 : 0"
        with open(path, "w") as f:
            f.write(f"""<graph id="TP2_InondationWorkflow">
  <version>1.0</version>
  <node id="Read"><operator>Read</operator><sources/>
    <parameters><file>{img}</file></parameters></node>
  <node id="Subset"><operator>Subset</operator>
    <sources><sourceProduct refid="Read"/></sources>
    <parameters>
      <geoRegion>POLYGON(({aoi['lon_min']} {aoi['lat_min']},{aoi['lon_max']} {aoi['lat_min']},{aoi['lon_max']} {aoi['lat_max']},{aoi['lon_min']} {aoi['lat_max']},{aoi['lon_min']} {aoi['lat_min']}))</geoRegion>
      <copyMetadata>true</copyMetadata>
    </parameters></node>
  <node id="Apply-Orbit-File"><operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="Subset"/></sources>
    <parameters><orbitType>Sentinel Precise (Auto Download)</orbitType><polyDegree>3</polyDegree><continueOnFail>false</continueOnFail></parameters></node>
  <node id="ThermalNoiseRemoval"><operator>ThermalNoiseRemoval</operator>
    <sources><sourceProduct refid="Apply-Orbit-File"/></sources>
    <parameters><selectedPolarisations>{pol}</selectedPolarisations><removeThermalNoise>true</removeThermalNoise></parameters></node>
  <node id="Calibration"><operator>Calibration</operator>
    <sources><sourceProduct refid="ThermalNoiseRemoval"/></sources>
    <parameters><selectedPolarisations>{pol}</selectedPolarisations><outputSigmaBand>true</outputSigmaBand></parameters></node>
  <node id="Speckle-Filter"><operator>Speckle-Filter</operator>
    <sources><sourceProduct refid="Calibration"/></sources>
    <parameters><sourceBands>Sigma0_{pol}</sourceBands><filter>Refined Lee</filter><filterSizeX>7</filterSizeX><filterSizeY>7</filterSizeY></parameters></node>
  <node id="Terrain-Correction"><operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="Speckle-Filter"/></sources>
    <parameters>
      <sourceBands>Sigma0_{pol}</sourceBands>
      <demName>{dem}</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>{px}</pixelSpacingInMeter>
      <mapProjection>EPSG:{epsg}</mapProjection>
      <nodataValueAtSea>false</nodataValueAtSea>
    </parameters></node>
  <node id="LinearToFromdB"><operator>LinearToFromdB</operator>
    <sources><sourceProduct refid="Terrain-Correction"/></sources>
    <parameters><sourceBands>Sigma0_{pol}</sourceBands></parameters></node>
  <node id="BandMaths"><operator>BandMaths</operator>
    <sources><sourceProduct refid="LinearToFromdB"/></sources>
    <parameters>
      <targetBands><targetBand>
        <name>inondation</name><type>int8</type>
        <expression>{expr}</expression>
        <noDataValue>-1</noDataValue>
      </targetBand></targetBands>
    </parameters></node>
  <node id="Write"><operator>Write</operator>
    <sources><sourceProduct refid="BandMaths"/></sources>
    <parameters><file>{out_mask}</file><formatName>GeoTIFF</formatName></parameters></node>
</graph>""")
        return path

    # ------------------------------------------------------------------
    # GÉNÉRATEUR XML SNAP — Prétraitement seul (TP1)
    # ------------------------------------------------------------------
    def _write_snap_graph_preprocess(self, img, aoi, pol, px, dem, epsg, out_tif):
        slug = Path(out_tif).stem
        path = os.path.join(self.outdir, f"snap_graph_{slug}.xml")
        with open(path, "w") as f:
            f.write(f"""<graph id="Preprocess_{slug}">
  <version>1.0</version>
  <node id="Read"><operator>Read</operator><sources/>
    <parameters><file>{img}</file></parameters></node>
  <node id="Subset"><operator>Subset</operator>
    <sources><sourceProduct refid="Read"/></sources>
    <parameters>
      <geoRegion>POLYGON(({aoi['lon_min']} {aoi['lat_min']},{aoi['lon_max']} {aoi['lat_min']},{aoi['lon_max']} {aoi['lat_max']},{aoi['lon_min']} {aoi['lat_max']},{aoi['lon_min']} {aoi['lat_min']}))</geoRegion>
      <copyMetadata>true</copyMetadata>
    </parameters></node>
  <node id="Apply-Orbit-File"><operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="Subset"/></sources>
    <parameters><orbitType>Sentinel Precise (Auto Download)</orbitType><polyDegree>3</polyDegree><continueOnFail>false</continueOnFail></parameters></node>
  <node id="ThermalNoiseRemoval"><operator>ThermalNoiseRemoval</operator>
    <sources><sourceProduct refid="Apply-Orbit-File"/></sources>
    <parameters><selectedPolarisations>{pol}</selectedPolarisations><removeThermalNoise>true</removeThermalNoise></parameters></node>
  <node id="Calibration"><operator>Calibration</operator>
    <sources><sourceProduct refid="ThermalNoiseRemoval"/></sources>
    <parameters><selectedPolarisations>{pol}</selectedPolarisations><outputSigmaBand>true</outputSigmaBand></parameters></node>
  <node id="Speckle-Filter"><operator>Speckle-Filter</operator>
    <sources><sourceProduct refid="Calibration"/></sources>
    <parameters><sourceBands>Sigma0_{pol}</sourceBands><filter>Refined Lee</filter><filterSizeX>7</filterSizeX><filterSizeY>7</filterSizeY></parameters></node>
  <node id="Terrain-Correction"><operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="Speckle-Filter"/></sources>
    <parameters>
      <sourceBands>Sigma0_{pol}</sourceBands>
      <demName>{dem}</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>{px}</pixelSpacingInMeter>
      <mapProjection>EPSG:{epsg}</mapProjection>
      <nodataValueAtSea>false</nodataValueAtSea>
    </parameters></node>
  <node id="LinearToFromdB"><operator>LinearToFromdB</operator>
    <sources><sourceProduct refid="Terrain-Correction"/></sources>
    <parameters><sourceBands>Sigma0_{pol}</sourceBands></parameters></node>
  <node id="Write"><operator>Write</operator>
    <sources><sourceProduct refid="LinearToFromdB"/></sources>
    <parameters><file>{out_tif}</file><formatName>GeoTIFF</formatName></parameters></node>
</graph>""")
        return path

    # ------------------------------------------------------------------
    # SCRIPT QGIS — Différence d'amplitude + RGB + masque (TP1)
    # ------------------------------------------------------------------
    def _write_diff_script(self, before_db, after_db, diff_tif, rgb_tif, out_mask):
        # TP1 utilise un seuil DIFFÉRENTIEL (before - after > X dB)
        # distinct du seuil absolu TP2 (backscatter < -26 dB)
        seuil_diff = self.p.get("seuil_diff_db", 3.0)   # 3 dB = standard SAR change detection
        path  = os.path.join(self.outdir, "diff_rgb.py")
        with open(path, "w") as f:
            f.write(f"""#!/usr/bin/env python3
import sys, os, numpy as np
from osgeo import gdal
gdal.UseExceptions()

before_db  = "{before_db}"
after_db   = "{after_db}"
diff_tif   = "{diff_tif}"
rgb_tif    = "{rgb_tif}"
out_mask   = "{out_mask}"
SEUIL_DIFF = {seuil_diff}   # seuil différentiel TP1 (before-after en dB)

# Aligner les images
import subprocess, os as _os
before_aligned = before_db.replace(".tif","_aligned.tif")
ds_a = gdal.Open(after_db)
gt   = ds_a.GetGeoTransform()
xs, ys = ds_a.RasterXSize, ds_a.RasterYSize
print(f"after_dB  : {{xs}}x{{ys}} px | gt={{gt[0]:.1f}},{{gt[3]:.1f}} res={{gt[1]:.1f}}")
_gdalwarp = _os.path.join("{GDAL_BIN}", "gdalwarp") if "{GDAL_BIN}" else "gdalwarp"
_warp_res = subprocess.run([_gdalwarp,
    "-t_srs", "EPSG:{self.p.get('epsg', 32629)}",
    "-tr", str(abs(gt[1])), str(abs(gt[5])),
    "-te", str(gt[0]), str(gt[3]+ys*gt[5]), str(gt[0]+xs*gt[1]), str(gt[3]),
    "-r","bilinear","-overwrite", before_db, before_aligned],
    capture_output=True, text=True)
if _warp_res.returncode != 0:
    print(f"gdalwarp ERREUR (code {{_warp_res.returncode}}): {{_warp_res.stderr[:300]}}")
else:
    print(f"gdalwarp OK → {{os.path.basename(before_aligned)}}")

USE_BLOCKS = _os.environ.get("USE_BLOCKS", "0") == "1"
_src = before_aligned if os.path.exists(before_aligned) else before_db
ds_b = gdal.Open(_src)
_bgt = ds_b.GetGeoTransform()
_align_status = "aligne" if _src == before_aligned else "NON ALIGNE gdalwarp echoue"
print(f"before_src: {{ds_b.RasterXSize}}x{{ds_b.RasterYSize}} px | gt={{_bgt[0]:.1f}},{{_bgt[3]:.1f}} res={{_bgt[1]:.1f}} ({{_align_status}})")
rows = min(ds_b.RasterYSize, ds_a.RasterYSize)
cols = min(ds_b.RasterXSize, ds_a.RasterXSize)
drv  = gdal.GetDriverByName("GTiff")
opts = ["COMPRESS=LZW", "TILED=YES"]
# Lire en forçant float32 quelle que soit le type natif SNAP (évite corruption si float64)
_GDT_F32 = gdal.GDT_Float32

if USE_BLOCKS:
    BLOCK = 2000
    out_diff = drv.Create(diff_tif, cols, rows, 1, _GDT_F32, opts)
    out_diff.SetGeoTransform(ds_a.GetGeoTransform()); out_diff.SetProjection(ds_a.GetProjection())
    out_diff.GetRasterBand(1).SetNoDataValue(-9999)
    out_msk  = drv.Create(out_mask, cols, rows, 1, gdal.GDT_Byte, opts)
    out_msk.SetGeoTransform(ds_a.GetGeoTransform()); out_msk.SetProjection(ds_a.GetProjection())
    out_msk.GetRasterBand(1).SetNoDataValue(255)
    n_flood = n_total = 0
    sum_b = sum_a = sum_b2 = sum_a2 = cnt = 0
    _diag_done = False
    for y0 in range(0, rows, BLOCK):
        h  = min(BLOCK, rows - y0)
        # buf_type=GDT_Float32 force la conversion → évite erreur si SNAP écrit en float64
        bd = np.frombuffer(ds_b.GetRasterBand(1).ReadRaster(0,y0,cols,h, buf_type=_GDT_F32), dtype=np.float32).reshape(h,cols)
        ad = np.frombuffer(ds_a.GetRasterBand(1).ReadRaster(0,y0,cols,h, buf_type=_GDT_F32), dtype=np.float32).reshape(h,cols)
        nd = ~np.isfinite(bd) | ~np.isfinite(ad) | (bd < -200) | (ad < -200)
        df = bd - ad; df[nd] = np.nan
        if not _diag_done:
            _vb = bd[~nd]; _va = ad[~nd]; _vd = df[~nd]
            print(f"[DIAG bloc0] before min={{_vb.min():.2f}} max={{_vb.max():.2f}} mean={{_vb.mean():.2f}} dB")
            print(f"[DIAG bloc0] after  min={{_va.min():.2f}} max={{_va.max():.2f}} mean={{_va.mean():.2f}} dB")
            print(f"[DIAG bloc0] diff   min={{_vd.min():.2f}} max={{_vd.max():.2f}} mean={{_vd.mean():.2f}} | pixels>3dB: {{int(np.sum(_vd>3.0)):,}}")
            _diag_done = True
        msk = np.where(nd, 255, (df > SEUIL_DIFF).astype(np.uint8))
        out_diff.GetRasterBand(1).WriteRaster(0,y0,cols,h, np.where(np.isnan(df),-9999,df).astype(np.float32).tobytes())
        out_msk.GetRasterBand(1).WriteRaster(0,y0,cols,h, msk.tobytes())
        vl = ~nd; n_flood += int(np.sum(msk==1)); n_total += int(np.sum(vl))
        bv=bd[vl]; av=ad[vl]; sum_b+=float(bv.sum()); sum_b2+=float((bv**2).sum()); sum_a+=float(av.sum()); sum_a2+=float((av**2).sum()); cnt+=bv.size
    out_diff.FlushCache(); out_msk.FlushCache()
    print(f"Seuil diff utilisé : {{SEUIL_DIFF}} dB")
    print(f"Pixels inondés : {{n_flood:,}} / {{n_total:,}} ({{n_flood/max(n_total,1)*100:.1f}}%)")
    mean_b=sum_b/max(cnt,1); std_b=max((sum_b2/max(cnt,1)-mean_b**2)**0.5, 1e-6)
    mean_a=sum_a/max(cnt,1); std_a=max((sum_a2/max(cnt,1)-mean_a**2)**0.5, 1e-6)
    lo_b,hi_b=mean_b-2*std_b,mean_b+2*std_b; lo_a,hi_a=mean_a-2*std_a,mean_a+2*std_a
    out_rgb = drv.Create(rgb_tif, cols, rows, 3, gdal.GDT_Byte, opts+["PHOTOMETRIC=RGB"])
    out_rgb.SetGeoTransform(ds_a.GetGeoTransform()); out_rgb.SetProjection(ds_a.GetProjection())
    for y0 in range(0, rows, BLOCK):
        h=min(BLOCK,rows-y0)
        bd=np.frombuffer(ds_b.GetRasterBand(1).ReadRaster(0,y0,cols,h,buf_type=_GDT_F32),dtype=np.float32).reshape(h,cols)
        ad=np.frombuffer(ds_a.GetRasterBand(1).ReadRaster(0,y0,cols,h,buf_type=_GDT_F32),dtype=np.float32).reshape(h,cols)
        def st(a,lo,hi): return np.clip((a-lo)/(hi-lo+1e-10)*255,0,255).astype(np.uint8)
        out_rgb.GetRasterBand(1).WriteRaster(0,y0,cols,h,st(bd,lo_b,hi_b).tobytes())
        out_rgb.GetRasterBand(2).WriteRaster(0,y0,cols,h,st(ad,lo_a,hi_a).tobytes())
        out_rgb.GetRasterBand(3).WriteRaster(0,y0,cols,h,st(ad,lo_a,hi_a).tobytes())
    out_rgb.FlushCache()
else:
    bd = ds_b.GetRasterBand(1).ReadAsArray().astype(np.float32)[:rows,:cols]
    ad = ds_a.GetRasterBand(1).ReadAsArray().astype(np.float32)[:rows,:cols]
    diff = bd - ad; nd = (bd < -200)|(ad < -200); diff[nd] = np.nan
    def save(path, arr, dtype=gdal.GDT_Float32, nd_val=None):
        o = drv.Create(path, cols, rows, 1, dtype, options=["COMPRESS=LZW"])
        o.SetGeoTransform(ds_a.GetGeoTransform()); o.SetProjection(ds_a.GetProjection())
        o.GetRasterBand(1).WriteArray(arr)
        if nd_val is not None: o.GetRasterBand(1).SetNoDataValue(nd_val)
        o.FlushCache()
    save(diff_tif, np.where(np.isnan(diff),-9999,diff), nd_val=-9999)
    mask = np.where(np.isnan(diff), 0, (diff > SEUIL_DIFF).astype(np.int8))
    n=int(np.sum(mask==1)); t=int(np.sum(~np.isnan(diff)))
    print(f"Seuil diff utilisé : {{SEUIL_DIFF}} dB")
    print(f"Pixels inondés : {{n:,}} / {{t:,}} ({{n/max(t,1)*100:.1f}}%)")
    save(out_mask, mask, gdal.GDT_Byte, 255); diff=None
    def stretch(a):
        v=a[np.isfinite(a)]; lo,hi=np.percentile(v,2),np.percentile(v,98)
        s=np.clip((a-lo)/(hi-lo+1e-10)*255,0,255); s[~np.isfinite(a)]=0; return s.astype(np.uint8)
    o = drv.Create(rgb_tif, cols, rows, 3, gdal.GDT_Byte, options=["COMPRESS=LZW","PHOTOMETRIC=RGB"])
    o.SetGeoTransform(ds_a.GetGeoTransform()); o.SetProjection(ds_a.GetProjection())
    for i,(band,ci) in enumerate(zip([stretch(bd),stretch(ad),stretch(ad)],[gdal.GCI_RedBand,gdal.GCI_GreenBand,gdal.GCI_BlueBand]),1):
        o.GetRasterBand(i).WriteArray(band); o.GetRasterBand(i).SetColorInterpretation(ci)
    o.FlushCache()
print("RGB sauvegardé:", rgb_tif)
""")
        return path

    # ------------------------------------------------------------------
    # SCRIPT PYTHON — Seuillage automatique TP2 (K-means)
    # ------------------------------------------------------------------
    def _write_tp2_mask_script(self, after_db, out_mask):
        path = os.path.join(self.outdir, "tp2_mask.py")
        use_blocks = USE_BLOCKS
        with open(path, "w") as f:
            f.write(f"""#!/usr/bin/env python3
import numpy as np, os
from osgeo import gdal
from scipy.cluster.vq import kmeans
gdal.UseExceptions()

after_db = "{after_db}"
out_mask = "{out_mask}"
USE_BLOCKS = {use_blocks}

ds = gdal.Open(after_db)
W, H = ds.RasterXSize, ds.RasterYSize
gt, prj = ds.GetGeoTransform(), ds.GetProjection()

# --- Echantillonnage pour K-means (1 ligne sur 20) ---
print("[TP2] Echantillonnage pour detection automatique du seuil...")
samp = []
step = max(1, H // 20)
for y in range(0, H, step):
    row = np.frombuffer(ds.GetRasterBand(1).ReadRaster(0, y, W, 1,
        buf_type=gdal.GDT_Float32), dtype=np.float32)
    # Exclure : NaN, < -200 dB (invalide), et = 0.0 (NoData SNAP hors-zone)
    v = row[np.isfinite(row) & (row > -200) & (row != 0.0)]
    if len(v): samp.append(v[:2000])

samp_arr = np.concatenate(samp).astype(np.float64) if samp else np.array([-26.0, -10.0])
ctr, _ = kmeans(samp_arr, 2)
ctr.sort()  # ctr[0]=eau (valeurs basses dB), ctr[1]=terre (valeurs hautes dB)
seuil_auto = float(ctr.mean())
print(f"[TP2] Centres K-means : eau={{ctr[0]:.2f}} dB | terre={{ctr[1]:.2f}} dB")
print(f"[TP2] Seuil automatique detecte : {{seuil_auto:.2f}} dB")
# Garde-fou : seuil toujours dans la plage réaliste SAR eau [-35, -15] dB
seuil_auto = max(-35.0, min(-15.0, seuil_auto))
print(f"[TP2] Seuil applique (apres garde-fou [-35,-15] dB) : {{seuil_auto:.2f}} dB")

# --- Appliquer le seuil ---
drv = gdal.GetDriverByName("GTiff")
out = drv.Create(out_mask, W, H, 1, gdal.GDT_Byte, ["COMPRESS=LZW","TILED=YES"])
out.SetGeoTransform(gt); out.SetProjection(prj)
out.GetRasterBand(1).SetNoDataValue(255)

n_water = n_total = 0
BLOCK = 2000
for y0 in range(0, H, BLOCK):
    h = min(BLOCK, H - y0)
    db = np.frombuffer(ds.GetRasterBand(1).ReadRaster(0, y0, W, h,
        buf_type=gdal.GDT_Float32), dtype=np.float32).reshape(h, W)
    nd = ~np.isfinite(db) | (db < -200) | (db == 0.0)
    msk = np.where(nd, 255, np.where(db < seuil_auto, 1, 0)).astype(np.uint8)
    out.GetRasterBand(1).WriteRaster(0, y0, W, h, msk.tobytes())
    n_water += int(np.sum(msk == 1))
    n_total += int(np.sum(~nd))

out.FlushCache()
print(f"[TP2] Pixels eau : {{n_water:,}} / {{n_total:,}} ({{n_water/max(n_total,1)*100:.1f}}%)")
print(f"[TP2] Masque eau sauvegarde : {{out_mask}}")
""")
        return path

    # ------------------------------------------------------------------
    # SCRIPT QGIS — Vectorisation + Stats (TP3)
    # ------------------------------------------------------------------
    def _write_tp3_script(self, mask_water, zi_shp, communes, stats_csv, prov_dir):
        area_min = self.p.get("area_min_ha", 0.5)
        path = os.path.join(self.outdir, "tp3_process.py")
        with open(path, "w") as f:
            f.write(f"""#!/usr/bin/env python3
import sys, os, csv, math, subprocess
from collections import defaultdict
from osgeo import gdal, ogr, osr
gdal.UseExceptions()

mask_water = "{mask_water}"
zi_shp     = "{zi_shp}"
communes   = "{communes}"
stats_csv  = "{stats_csv}"
prov_dir   = "{prov_dir}"
AREA_MIN   = {area_min}

# --- A: Lissage ---
import numpy as np, os as _os
from scipy.ndimage import gaussian_filter, uniform_filter
USE_BLOCKS = _os.environ.get("USE_BLOCKS", "0") == "1"
print(f"[A] Lissage du masque eau ({'blocs' if USE_BLOCKS else 'direct'})...")
drv = gdal.GetDriverByName("GTiff")
ds  = gdal.Open(mask_water)
W, H = ds.RasterXSize, ds.RasterYSize
gt, prj = ds.GetGeoTransform(), ds.GetProjection()
# Détecter le type réel du raster (int8 SNAP → GDT_Byte ou GDT_Int16 selon GDAL)
_dt = ds.GetRasterBand(1).DataType
_dt_map = {{1: np.uint8, 2: np.uint16, 3: np.int16, 5: np.int32, 6: np.float32, 7: np.float64}}
_raw_dtype = _dt_map.get(_dt, np.uint8)
smoothed_tif = mask_water.replace(".tif","_smoothed.tif")
o = drv.Create(smoothed_tif, W, H, 1, gdal.GDT_Float32, options=["COMPRESS=LZW","TILED=YES"])
o.SetGeoTransform(gt); o.SetProjection(prj)
if USE_BLOCKS:
    BLOCK, PAD = 1000, 8
    band = ds.GetRasterBand(1)
    _bps = np.dtype(_raw_dtype).itemsize
    for y0 in range(0, H, BLOCK):
        y_read = max(0, y0 - PAD); y_end = min(H, y0 + BLOCK + PAD)
        h_read = y_end - y_read
        raw_raw = np.frombuffer(band.ReadRaster(0, y_read, W, h_read, buf_type=_dt), dtype=_raw_dtype).reshape(h_read, W)
        nd_mask = (raw_raw <= 0) | (raw_raw >= 2)  # nodata: 255(uint8) ou -1(int) ou 0 = non-eau
        raw_f = raw_raw.astype(np.float32)
        raw_f[nd_mask & (raw_raw != 1)] = 0.0  # zeros non-eau, garde les 1 (eau)
        raw_f[raw_raw > 1] = 0.0               # masque nodata (255, -1, etc.) → 0 avant lissage
        sm  = uniform_filter(raw_f, size=5)
        sm[raw_raw > 1] = np.nan               # nodata → NaN dans le résultat lissé
        y_s = y0 - y_read; chunk = sm[y_s:y_s + min(BLOCK, H - y0), :]
        chunk_out = np.where(np.isnan(chunk), -9999.0, chunk).astype(np.float32)
        o.GetRasterBand(1).WriteRaster(0, y0, W, chunk.shape[0], chunk_out.tobytes())
    band = None
    o.GetRasterBand(1).SetNoDataValue(-9999.0)
else:
    data = ds.GetRasterBand(1).ReadAsArray()
    nd_mask = (data > 1) | (data < 0)
    data_f = np.where(nd_mask, 0.0, data).astype(np.float64)
    sm   = gaussian_filter(data_f, sigma=2.0).astype(np.float32)
    sm[nd_mask] = -9999.0
    o.GetRasterBand(1).SetNoDataValue(-9999.0)
    o.GetRasterBand(1).WriteArray(sm); data = None; sm = None
o.FlushCache(); o = None; ds = None

# --- B: Reclassification (seuil fixe robuste — remplace kmeans fragile) ---
# Le masque lissé a des valeurs 0.0–1.0 pour les pixels valides.
# Un pixel eau isolé (1 sur fond 0, filtre 5×5) donne ~0.04.
# Un groupe de 3×3 pixels eau donne ~0.36. Seuil 0.3 = zone ≥ ~3×3 px (10m).
print("[B] Reclassification...")
ds_s = gdal.Open(smoothed_tif)
W2, H2 = ds_s.RasterXSize, ds_s.RasterYSize
# Échantillonner pour statistiques diagnostiques uniquement
_samp_rows = []; _step = max(1, H2 // 20)
for _y in range(0, H2, _step):
    _row = np.frombuffer(ds_s.GetRasterBand(1).ReadRaster(0, _y, W2, 1), dtype=np.float32)
    _v = _row[np.isfinite(_row) & (_row >= 0)]
    if len(_v): _samp_rows.append(_v[:2000])
_samp = np.concatenate(_samp_rows) if _samp_rows else np.array([0.0])
_pos  = _samp[_samp > 0.02]
n_pos = len(_pos)
thr = 0.30  # seuil fixe — robuste même si masque sparse ou vide
print(f"  Pixels actifs (>0.02): {{n_pos:,}} / {{len(_samp):,}} | Seuil: {{thr:.2f}}")
reclass_tif = mask_water.replace(".tif","_reclass.tif")
o = drv.Create(reclass_tif, W2, H2, 1, gdal.GDT_Int16, options=["COMPRESS=LZW","TILED=YES"])
o.SetGeoTransform(ds_s.GetGeoTransform()); o.SetProjection(ds_s.GetProjection())
o.GetRasterBand(1).SetNoDataValue(0)
if USE_BLOCKS:
    BLOCK = 1000
    for y0 in range(0, H2, BLOCK):
        h = min(BLOCK, H2 - y0)
        row = np.frombuffer(ds_s.GetRasterBand(1).ReadRaster(0, y0, W2, h), dtype=np.float32).reshape(h, W2)
        nd  = ~np.isfinite(row) | (row < 0)
        rc  = np.where(nd, 0, np.where(row >= thr, 2, 1)).astype(np.int16)
        o.GetRasterBand(1).WriteRaster(0, y0, W2, h, rc.tobytes())
else:
    data = ds_s.GetRasterBand(1).ReadAsArray().astype(np.float32)
    nd   = ~np.isfinite(data) | (data < 0)
    reclass = np.where(nd, 0, np.where(data >= thr, 2, 1)).astype(np.int16)
    o.GetRasterBand(1).WriteArray(reclass); data = None; reclass = None
o.FlushCache(); o = None; ds_s = None

# --- C: Vectorisation ---
print("[C] Vectorisation...")

# Rééchantillonner à 30m avant polygonisation (divise par ~9 le nb de pixels → 9x plus rapide)
reclass_30m = reclass_tif.replace(".tif", "_30m.tif")
import os as _os
_gdalwarp2 = _os.path.join("{GDAL_BIN}", "gdalwarp") if "{GDAL_BIN}" else "gdalwarp"
subprocess.run([_gdalwarp2, "-tr", "30", "30", "-r", "near",
    "-co", "COMPRESS=LZW", "-overwrite", reclass_tif, reclass_30m],
    capture_output=True)
poly_src = reclass_30m if os.path.exists(reclass_30m) else reclass_tif
print(f"  Raster source polygonize: {{os.path.basename(poly_src)}}")

raw_shp = zi_shp.replace(".shp","_raw.shp")

from osgeo import gdal_array
ds_r = gdal.Open(poly_src)
band_r = ds_r.GetRasterBand(1)
drv_shp = ogr.GetDriverByName("ESRI Shapefile")
if os.path.exists(raw_shp): drv_shp.DeleteDataSource(raw_shp)
raw_ds  = drv_shp.CreateDataSource(raw_shp)
raw_srs = osr.SpatialReference()
raw_srs.ImportFromWkt(ds_r.GetProjection())
raw_lay = raw_ds.CreateLayer("zi", srs=raw_srs, geom_type=ogr.wkbPolygon)
fd = ogr.FieldDefn("gridcode", ogr.OFTInteger)
raw_lay.CreateField(fd)
gdal.Polygonize(band_r, band_r, raw_lay, 0, [], callback=None)
raw_ds.FlushCache(); raw_ds = None; ds_r = None
print(f"  Polygonize terminé: {{raw_shp}}")

drv_shp = ogr.GetDriverByName("ESRI Shapefile")
src = ogr.Open(raw_shp); src_lay = src.GetLayer()
if os.path.exists(zi_shp): drv_shp.DeleteDataSource(zi_shp)
out_ds = drv_shp.CreateDataSource(zi_shp)
srs    = src_lay.GetSpatialRef()
out_lay = out_ds.CreateLayer("ZI", srs=srs, geom_type=ogr.wkbPolygon)
fld = ogr.FieldDefn("Surface_ha", ogr.OFTReal); fld.SetWidth(15); fld.SetPrecision(4)
out_lay.CreateField(fld)
n_ok, n_skip = 0, 0
for feat in src_lay:
    if feat.GetField("gridcode") != 2: continue
    geom = feat.GetGeometryRef()
    if geom is None: continue
    area = geom.Area() / 10000.0
    if area < AREA_MIN: n_skip += 1; continue
    of = ogr.Feature(out_lay.GetLayerDefn())
    of.SetGeometry(geom.Clone()); of.SetField("Surface_ha", round(area,4))
    out_lay.CreateFeature(of); n_ok += 1
src = None; out_ds = None
print(f"  Polygones: {{n_ok}} conservés, {{n_skip}} supprimés (<{{AREA_MIN}} ha)")

# --- D: Statistiques par commune ---
print("[D] Statistiques par commune...")
if not os.path.exists(communes):
    print("  Couche communes introuvable - stats globales uniquement")
    total = 0.0
    zi_ds = ogr.Open(zi_shp); zi_lay = zi_ds.GetLayer()
    for feat in zi_lay: total += feat.GetField("Surface_ha") or 0
    zi_ds = None
    with open(stats_csv,"w") as f: f.write(f"Type,Valeur\\nSurface_totale_ha,{{total:.2f}}\\n")
    print(f"  Surface totale: {{total:,.2f}} ha")
else:
    # Reprojeter ZI en WGS84
    wgs84 = osr.SpatialReference(); wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    zi_ds = ogr.Open(zi_shp); zi_lay = zi_ds.GetLayer()
    zi_srs= zi_lay.GetSpatialRef()
    tr    = osr.CoordinateTransformation(zi_srs, wgs84)
    zi_wgs = zi_shp.replace(".shp","_wgs84.shp")
    if os.path.exists(zi_wgs): drv_shp.DeleteDataSource(zi_wgs)
    o_ds  = drv_shp.CreateDataSource(zi_wgs)
    o_lay = o_ds.CreateLayer("ZI_wgs84", srs=wgs84, geom_type=ogr.wkbPolygon)
    o_lay.CreateField(ogr.FieldDefn("Surface_ha", ogr.OFTReal))
    zi_lay.ResetReading()
    for feat in zi_lay:
        g = feat.GetGeometryRef()
        if g:
            gc = g.Clone(); gc.Transform(tr)
            of = ogr.Feature(o_lay.GetLayerDefn())
            of.SetGeometry(gc); of.SetField("Surface_ha", feat.GetField("Surface_ha") or 0)
            o_lay.CreateFeature(of)
    zi_ds = None; o_ds = None

    # Envelope ZI (sans union global — trop lent)
    zi_ds = ogr.Open(zi_wgs); zi_lay = zi_ds.GetLayer()
    env = zi_lay.GetExtent()   # (minX, maxX, minY, maxY)
    zi_ds = None

    lat0 = (env[2]+env[3])/2; cos_lat = math.cos(math.radians(lat0))
    ha_per_sq_deg = (111000**2)*cos_lat/10000

    # Intersection par commune via SetSpatialFilter (évite le Union global)
    com_ds = ogr.Open(communes); com_lay = com_ds.GetLayer()
    com_lay.SetSpatialFilterRect(env[0], env[2], env[1], env[3])
    stats = defaultdict(float)
    for com_feat in com_lay:
        cg = com_feat.GetGeometryRef()
        if cg is None: continue
        # Filtrer les ZI polygones proches de cette commune
        zi_ds2 = ogr.Open(zi_wgs); zi_lay2 = zi_ds2.GetLayer()
        zi_lay2.SetSpatialFilter(cg)
        area_com = 0.0
        for zi_feat in zi_lay2:
            zg = zi_feat.GetGeometryRef()
            if zg is None: continue
            inter = cg.Intersection(zg)
            if inter is None or inter.IsEmpty(): continue
            area_com += inter.Area() * ha_per_sq_deg
        zi_ds2 = None
        if area_com < 0.01: continue
        r = com_feat.GetField("NAME_1") or "Inconnue"
        p = com_feat.GetField("NAME_2") or "Inconnue"
        c = com_feat.GetField("NAME_4") or com_feat.GetField("NAME_3") or "Inconnue"
        stats[(r,p,c)] += area_com
    com_ds = None

    # CSV global
    with open(stats_csv,"w",encoding="utf-8",newline="") as f:
        w = csv.writer(f)
        w.writerow(["Region","Province","Commune","Surface_ZI_ha"])
        for (r,p,c),a in sorted(stats.items(),key=lambda x:(x[0][1],-x[1])):
            w.writerow([r,p,c,f"{{a:.2f}}"])
        w.writerow(["TOTAL","","",f"{{sum(stats.values()):.2f}}"])

    # Split par province
    by_prov = defaultdict(list)
    for (r,p,c),a in stats.items(): by_prov[(r,p)].append((c,a))
    os.makedirs(prov_dir, exist_ok=True)
    for (r,p),coms in sorted(by_prov.items()):
        fn = os.path.join(prov_dir, p.replace(" ","_").replace("/","-")+".csv")
        with open(fn,"w",encoding="utf-8",newline="") as f:
            w = csv.writer(f)
            w.writerow(["Province","Commune","Surface_ZI_ha"])
            for c,a in sorted(coms, key=lambda x:-x[1]): w.writerow([p,c,f"{{a:.2f}}"])
            w.writerow(["TOTAL","",f"{{sum(a for _,a in coms):.2f}}"])

    total = sum(stats.values())
    print(f"  Surface totale: {{total:,.2f}} ha | {{len(stats)}} communes | {{len(by_prov)}} provinces")

print("[TP3] Terminé")
""")
        return path

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _run_snap_graph(self, graph_xml, label="SNAP"):
        job = self.job
        job.log(f"Lancement SNAP: {label}")
        snap_xmx = os.environ.get("SNAP_XMX", "4G")
        env = {**os.environ, "JAVA_OPTS": f"-Xmx{snap_xmx}"}
        proc = subprocess.Popen(
            [SNAP_GPT, graph_xml, f"-J-Xmx{snap_xmx}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env
        )
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            # Log toutes les lignes utiles (INFO, %, erreurs, exceptions)
            if any(k in line for k in ["INFO:", "%", "done", "ERROR", "SEVERE", "Exception", "Warning", "WARN", "at com.", "cause-"]):
                job.log(line, "SNAP")
            if "% " in line or "done" in line:
                try:
                    pct_str = line.split("%")[0].split(".")[-1].strip()
                    pct = int(pct_str)
                    base = {"TP1-BEFORE": 5, "TP1-AFTER": 25, "TP2-SNAP": 10, "TP2": 10}.get(label, 0)
                    span = 20
                    self.job.progress = min(base + int(pct * span / 100), 95)
                    self.job._save_state()
                except:
                    pass
        proc.wait()
        success = proc.returncode == 0
        job.log(f"SNAP {label}: {'OK' if success else 'ERREUR (code ' + str(proc.returncode) + ')'}")
        return success

    def _run_qgis_script(self, script_path, label="QGIS"):
        job = self.job
        job.log(f"Lancement QGIS/Python: {label}")
        env = {**os.environ, **QGIS_ENV}
        proc = subprocess.Popen(
            [PYTHON_QGIS, script_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env
        )
        for line in proc.stdout:
            line = line.strip()
            if line and "FutureWarning" not in line and "warnings.warn" not in line:
                job.log(line, "QGIS")
        proc.wait()
        ok = proc.returncode == 0
        job.log(f"QGIS {label}: {'OK' if ok else 'ERREUR code ' + str(proc.returncode)}")
        return ok

    def _check_cancelled(self):
        """Relit le state.json pour détecter une annulation externe."""
        import json as _json
        state_file = os.path.join(self.job.outdir, "state.json")
        try:
            with open(state_file) as f:
                s = _json.load(f)
            if s.get("status") == "cancelled":
                raise _CancelledError()
        except _CancelledError:
            raise
        except Exception:
            pass

    def _find_gadm(self):
        candidates = [
            GADM_DEFAULT,
            os.path.join(RESULTS_DIR, "..", "outputs", "TP3", "gadm41_MAR_4.shp"),
            "/app/data/gadm/gadm41_MAR_4.shp",
            "/Users/mac/Documents/Projet/CRTS/innodation/outputs/TP3/gadm41_MAR_4.shp",
        ]
        for c in candidates:
            if c and os.path.exists(os.path.normpath(c)):
                return os.path.normpath(c)
        return ""

    # ------------------------------------------------------------------
    # RAPPORT HTML
    # ------------------------------------------------------------------
    def _build_report_html(self, rows, total):
        params = self.p
        now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        job = self.job

        rows_html = ""
        if rows:
            for r in rows[:50]:
                rows_html += f"""<tr>
                    <td>{r.get('Region','')}</td>
                    <td><b>{r.get('Province','')}</b></td>
                    <td>{r.get('Commune','')}</td>
                    <td class="num">{float(r.get('Surface_ZI_ha',0)):,.2f}</td>
                </tr>\n"""
        else:
            rows_html = "<tr><td colspan='4'>Données non disponibles</td></tr>"

        files_html = ""
        for key, path in job.results.items():
            if path and os.path.exists(str(path)):
                size = os.path.getsize(path)
                size_str = f"{size/1e6:.1f} MB" if size > 1e6 else f"{size/1e3:.0f} KB"
                fname = os.path.basename(path)
                files_html += f"<li><code>{fname}</code> <span class='fsize'>({size_str})</span></li>\n"

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport Inondation — CRTS</title>
<style>
  * {{ box-sizing: border-box; margin:0; padding:0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#0f1623; color:#e0e8f0; }}
  header {{ background:linear-gradient(135deg,#1a3a5c,#0d5c8a); padding:24px 32px; border-bottom:3px solid #2196f3; }}
  header h1 {{ font-size:1.6em; color:#fff; }} header p {{ color:#90caf9; margin-top:4px; }}
  .container {{ max-width:1100px; margin:0 auto; padding:24px 16px; }}
  .grid3 {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin:24px 0; }}
  .card {{ background:#162032; border:1px solid #1e3a55; border-radius:10px; padding:20px; text-align:center; }}
  .card .val {{ font-size:2em; font-weight:700; color:#2196f3; }}
  .card .lbl {{ font-size:.85em; color:#78909c; margin-top:4px; }}
  .section {{ background:#162032; border:1px solid #1e3a55; border-radius:10px; padding:24px; margin:16px 0; }}
  .section h2 {{ color:#64b5f6; border-bottom:1px solid #1e3a55; padding-bottom:10px; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; font-size:.9em; }}
  th {{ background:#1a3a5c; color:#90caf9; padding:10px 12px; text-align:left; }}
  td {{ padding:8px 12px; border-bottom:1px solid #1e3a55; }}
  td.num {{ text-align:right; font-weight:600; color:#4fc3f7; }}
  tr:hover td {{ background:#1a2a3a; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:12px; font-size:.8em; }}
  .badge.done {{ background:#1b5e20; color:#a5d6a7; }}
  .badge.error {{ background:#b71c1c; color:#ffcdd2; }}
  .params {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:.9em; }}
  .params .row {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1e3a55; }}
  .params .key {{ color:#78909c; }} .params .val2 {{ color:#e0e8f0; }}
  ul.files {{ list-style:none; padding:0; }} ul.files li {{ padding:6px 0; border-bottom:1px solid #1e3a55; }}
  ul.files code {{ color:#4fc3f7; }} .fsize {{ color:#546e7a; font-size:.85em; }}
  .footer {{ text-align:center; color:#37474f; font-size:.8em; padding:32px; }}
</style>
</head>
<body>
<header>
  <h1>🌊 Rapport Cartographie Zones Inondées</h1>
  <p>CRTS — Centre Royal de Télédétection Spatiale &nbsp;|&nbsp; Généré le {now}</p>
</header>
<div class="container">
  <div class="grid3">
    <div class="card">
      <div class="val">{total:,.0f}</div>
      <div class="lbl">ha inondés détectés</div>
    </div>
    <div class="card">
      <div class="val">{total/100:,.0f}</div>
      <div class="lbl">km² affectés</div>
    </div>
    <div class="card">
      <div class="val">{len(rows)}</div>
      <div class="lbl">communes touchées</div>
    </div>
  </div>

  <div class="section">
    <h2>📋 Paramètres du traitement</h2>
    <div class="params">
      <div class="row"><span class="key">Polarisation</span><span class="val2">{params.get('polarisation','VH')}</span></div>
      <div class="row"><span class="key">Résolution</span><span class="val2">{params.get('pixel_spacing',10)} m</span></div>
      <div class="row"><span class="key">DEM</span><span class="val2">{params.get('dem','SRTM 1Sec HGT')}</span></div>
      <div class="row"><span class="key">Filtre Speckle</span><span class="val2">{params.get('speckle_filter','Refined Lee')}</span></div>
      <div class="row"><span class="key">Seuil détection</span><span class="val2">{params.get('seuil_db',-26)} dB</span></div>
      <div class="row"><span class="key">Zone d'intérêt</span><span class="val2">{params.get('aoi',{}).get('lon_min','')}°/{params.get('aoi',{}).get('lat_min','')}° → {params.get('aoi',{}).get('lon_max','')}°/{params.get('aoi',{}).get('lat_max','')}°</span></div>
      <div class="row"><span class="key">Projection</span><span class="val2">EPSG:{params.get('epsg',32629)} (UTM 29N)</span></div>
      <div class="row"><span class="key">Surface min polygone</span><span class="val2">{params.get('area_min_ha',0.5)} ha</span></div>
    </div>
  </div>

  <div class="section">
    <h2>📊 Surface inondée par commune (Top 50)</h2>
    <table>
      <thead><tr><th>Région</th><th>Province</th><th>Commune</th><th>Surface ZI (ha)</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>📁 Fichiers produits</h2>
    <ul class="files">{files_html}</ul>
  </div>
</div>
<div class="footer">Plateforme Gestion de Crise Inondation — CRTS/DEP &nbsp;|&nbsp; Traitement SAR Sentinel-1 via ESA SNAP + QGIS/GDAL</div>
</body></html>"""
