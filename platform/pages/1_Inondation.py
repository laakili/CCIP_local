"""
CCIP — Module Gestion de Crise Inondation
Traitement SAR Sentinel-1 automatisé : TP1 + TP2 + TP3
"""

import os, sys, json, uuid, threading, time, datetime, zipfile, io, base64
import streamlit as st
import streamlit.components.v1 as _stc
import pandas as pd

_PLATFORM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENTINEL_DIR = os.environ.get("SENTINEL_DATA_DIR",
    os.path.join(_PLATFORM_DIR, "..", "data", "sentinel"))
SENTINEL_DIR = os.path.normpath(SENTINEL_DIR)
os.makedirs(SENTINEL_DIR, exist_ok=True)

def save_upload(uploaded_file) -> str:
    dest = os.path.join(SENTINEL_DIR, uploaded_file.name)
    if not os.path.exists(dest):
        with open(dest, "wb") as f:
            f.write(uploaded_file.getbuffer())
    return dest

PLATFORM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Logo CRTS
_logo_path = os.path.join(PLATFORM_DIR, "static", "crts_logo.png")
with open(_logo_path, "rb") as _f:
    CRTS_LOGO_B64 = f"data:image/png;base64,{base64.b64encode(_f.read()).decode()}"
sys.path.insert(0, PLATFORM_DIR)
from core.pipeline import FloodPipeline, Job
from core.config   import RESULTS_DIR, DEFAULT_PARAMS

st.set_page_config(
    page_title="CCIP — Inondation",
    page_icon=_logo_path if os.path.exists(_logo_path) else "🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Inter:wght@300;400;500;600&display=swap');

.stApp { background: #020b18 !important; }
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0a1628 0%, #0d1f35 100%) !important;
  border-right: 1px solid rgba(33,150,243,0.15) !important;
  top: 60px !important;
}
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }

/* Sidebar toujours visible — non collapsable */
section[data-testid="stSidebar"] {
  transform: none !important;
  visibility: visible !important;
  display: block !important;
  min-width: 21rem !important;
}
[data-testid="collapsedControl"] { display: none !important; }

/* Décaler le contenu principal sous la navbar */
.block-container { padding-top: 76px !important; }

/* ── NAVBAR ── */
@keyframes blink   { 0%,100%{opacity:1} 50%{opacity:.2} }
@keyframes spin    { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
.ccip-nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
  height: 60px;
  background: rgba(2,11,24,0.95);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(33,150,243,0.2);
  display: flex; align-items: center;
  padding: 0 32px; gap: 0;
}
.nav-logo {
  display: flex; align-items: center; gap: 10px;
  text-decoration: none; flex-shrink: 0;
}
.nav-emblem {
  width: 32px; height: 32px; position: relative; flex-shrink: 0;
}
.nav-ring {
  position: absolute; border-radius: 50%; border: 1.5px solid #2196f3;
}
.nav-logo-img {
  width: 36px; height: 36px; object-fit: contain;
  background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.06) 55%, transparent 75%);
  border-radius: 50%;
  padding: 3px;
  filter: drop-shadow(0 0 8px rgba(255,255,255,0.35)) brightness(1.15);
}
.nav-brand {
  font-family: 'Orbitron', monospace;
  font-size: .9em; font-weight: 700;
  color: #90caf9; letter-spacing: 2px;
}
.nav-brand span { color: rgba(144,202,249,0.4); font-size:.75em; margin-left:4px; }
.nav-sep {
  width: 1px; height: 28px;
  background: rgba(33,150,243,0.2);
  margin: 0 24px; flex-shrink: 0;
}
.nav-crises-label {
  font-family: 'Orbitron', monospace;
  font-size: .62em; color: rgba(33,150,243,0.5);
  letter-spacing: 3px; margin-right: 16px; flex-shrink: 0;
  text-transform: uppercase;
}
.nav-crisis-items { display: flex; align-items: center; gap: 6px; flex: 1; }
.nav-crisis-item {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 14px; border-radius: 20px;
  font-family: 'Inter', sans-serif; font-size: .78em; font-weight: 500;
  text-decoration: none; cursor: pointer;
  transition: all .2s; white-space: nowrap;
  border: 1px solid transparent;
  color: rgba(144,202,249,0.45); background: transparent;
}
.nav-crisis-item:hover { color:#90caf9; background:rgba(33,150,243,0.08); border-color:rgba(33,150,243,0.2); }
.nav-crisis-item.nav-active {
  color: #e3f2fd; background: rgba(33,150,243,0.15); border-color: rgba(33,150,243,0.4);
}
.nav-crisis-item.nav-disabled { opacity:.35; cursor:default; pointer-events:none; }
.dot-active {
  width: 5px; height: 5px; border-radius: 50%;
  background: #4fc3f7; box-shadow: 0 0 5px #4fc3f7;
  animation: blink 1.5s ease-in-out infinite;
}
.nav-right { display:flex; align-items:center; gap:14px; margin-left:auto; flex-shrink:0; }
.nav-status {
  display:flex; align-items:center; gap:6px;
  font-family:'Orbitron',monospace; font-size:.62em; color:rgba(144,202,249,0.5);
}
.nav-status-dot {
  width:6px; height:6px; border-radius:50%;
  background:#66bb6a; box-shadow:0 0 5px #66bb6a;
  animation:blink 1.5s ease-in-out infinite;
}
.nav-version {
  font-family:'Orbitron',monospace; font-size:.6em;
  color:rgba(33,150,243,0.3); border:1px solid rgba(33,150,243,0.15);
  padding:2px 8px; border-radius:10px;
}

/* Header module */
.module-header {
  background: linear-gradient(135deg, rgba(13,33,57,0.95), rgba(6,18,36,0.98));
  border: 1px solid rgba(33,150,243,0.25);
  border-left: 4px solid #2196f3;
  border-radius: 12px; padding: 20px 28px; margin-bottom: 24px;
  display: flex; align-items: center; justify-content: space-between;
}
.module-header-left { display: flex; align-items: center; gap: 16px; }
.module-icon { font-size: 2.2em; filter: drop-shadow(0 0 12px rgba(33,150,243,0.7)); }
.module-title { font-family: 'Orbitron', monospace; }
.module-title h2 { color: #e3f2fd; font-size: 1.2em; font-weight: 700; margin: 0; }
.module-title p  { color: #64b5f6; font-size: .8em; margin: 4px 0 0; }
.module-nav a {
  color: rgba(144,202,249,0.6); font-size: .82em; text-decoration: none;
  font-family: 'Inter', sans-serif;
  padding: 6px 14px; border: 1px solid rgba(33,150,243,0.2);
  border-radius: 20px; transition: all .2s;
}
.module-nav a:hover { color: #90caf9; border-color: rgba(33,150,243,0.5); }

/* Sidebar labels */
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #64b5f6 !important; }
[data-testid="stSidebar"] label { color: #90a4ae !important; font-size: .85em !important; }

/* Métriques */
[data-testid="metric-container"] {
  background: linear-gradient(145deg, #0d2137, #0a1828);
  border: 1px solid rgba(33,150,243,0.2); border-radius: 10px; padding: 16px;
}
[data-testid="stMetricValue"]  { color: #2196f3 !important; font-family: 'Orbitron', monospace !important; }
[data-testid="stMetricLabel"]  { color: #546e7a !important; font-size: .8em !important; }

/* Cards */
.result-card {
  background: linear-gradient(145deg, #0d2137, #0a1828);
  border: 1px solid rgba(33,150,243,0.2); border-radius: 10px;
  padding: 16px 20px; margin-bottom: 12px;
}
.result-card h4 { color: #64b5f6; margin: 0 0 8px; font-size: .9em; }

/* Logs */
.log-box {
  background: #030d1a; border: 1px solid rgba(33,150,243,0.15);
  border-radius: 8px; padding: 14px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: .78em; max-height: 280px; overflow-y: auto;
  line-height: 1.6;
}
.log-snap  { color: #26a69a; }
.log-qgis  { color: #7986cb; }
.log-warn  { color: #ffa726; }
.log-error { color: #ef5350; }
.log-info  { color: #37474f; }
.log-ts    { color: #1e3a55; margin-right: 8px; }

/* Badge statuts */
.badge { padding: 3px 12px; border-radius: 20px; font-size: .75em; font-weight: 600; }
.badge-done    { background:#1b3a1e; color:#81c784; }
.badge-running { background:#0d3a5c; color:#4fc3f7; }
.badge-error   { background:#3a1010; color:#ef9a9a; }
.badge-pending { background:#1a2a3a; color:#78909c; }

/* Pipeline étapes */
.pipeline-step {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; margin: 4px 0;
  background: rgba(13,33,57,0.6); border-radius: 8px;
  font-family: 'Inter', sans-serif; font-size: .85em;
}
.step-num {
  width: 24px; height: 24px; border-radius: 50%;
  background: rgba(33,150,243,0.2); border: 1px solid rgba(33,150,243,0.4);
  display: flex; align-items: center; justify-content: center;
  font-size: .75em; color: #64b5f6; font-weight: 700; flex-shrink: 0;
}
.step-label { color: #90a4ae; }
.step-detail { color: #546e7a; font-size: .85em; margin-left: auto; }

/* Tableau */
.stDataFrame { border: 1px solid rgba(33,150,243,0.15) !important; border-radius: 8px !important; }

/* Divider */
hr { border-color: rgba(33,150,243,0.1) !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #020b18; }
::-webkit-scrollbar-thumb { background: #1a3050; border-radius: 3px; }

</style>
""", unsafe_allow_html=True)

# ── Chargement des jobs ───────────────────────────────────────
@st.cache_resource
def load_jobs() -> dict:
    jobs = {}
    if not os.path.exists(RESULTS_DIR):
        return jobs
    for jid in os.listdir(RESULTS_DIR):
        sf = os.path.join(RESULTS_DIR, jid, "state.json")
        if os.path.exists(sf):
            try:
                with open(sf) as f: s = json.load(f)
                j = Job(jid, s.get("params", {}))
                status = s.get("status", "unknown")
                # Un job "running" au démarrage = le processus a été tué → interrompu
                if status == "running":
                    status = "error"
                    s.setdefault("logs", []).append({
                        "ts": "—", "level": "ERROR",
                        "msg": "Job interrompu (redémarrage serveur)"
                    })
                j.status   = status
                j.progress = s.get("progress", 0)
                j.logs     = s.get("logs", [])
                j.results  = s.get("results", {})
                j.created  = s.get("created", "")
                j.finished = s.get("finished", "")
                jobs[jid]  = j
            except: pass
    return jobs

JOBS = load_jobs()

def reload_job(jid):
    sf = os.path.join(RESULTS_DIR, jid, "state.json")
    if not os.path.exists(sf):
        return JOBS.get(jid)
    try:
        with open(sf) as f:
            content = f.read().strip()
            s = json.loads(content) if content else {}
    except (json.JSONDecodeError, OSError):
        s = {}
    j = JOBS.get(jid) or Job(jid, s.get("params", {}))
    j.status   = s.get("status", j.status)
    j.progress = s.get("progress", j.progress)
    j.logs     = s.get("logs", j.logs)
    j.results  = s.get("results", j.results)
    j.finished = s.get("finished", j.finished)
    JOBS[jid]  = j
    return j

def launch_job(params: dict) -> str:
    jid = uuid.uuid4().hex[:12]
    job = Job(jid, params)
    JOBS[jid] = job
    threading.Thread(target=lambda: FloodPipeline(job).run(), daemon=True).start()
    return jid

def fmt_date(iso):
    if not iso: return ""
    try: return datetime.datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except: return iso

def status_badge(s):
    cls = {"done":"done","running":"running","error":"error"}.get(s,"pending")
    lbl = {"done":"✓ Terminé","running":"⏳ En cours","error":"✗ Erreur",
           "pending":"En attente","cancelled":"Annulé"}.get(s, s)
    return f"<span class='badge badge-{cls}'>{lbl}</span>"

# ═══════════════════════════════════════════════════════════════
# NAVBAR
# ═══════════════════════════════════════════════════════════════
st.markdown(f"""
<nav class="ccip-nav">
  <a class="nav-logo" href="/" target="_self">
    <img class="nav-logo-img" src="{CRTS_LOGO_B64}" alt="CRTS">
    <div class="nav-brand">CCIP <span>· CRTS</span></div>
  </a>
  <div class="nav-sep"></div>
  <div class="nav-crises-label">Crises</div>
  <div class="nav-crisis-items">
    <a class="nav-crisis-item nav-active" href="/Inondation" target="_self">
      <div class="dot-active"></div>
      🌊 Inondation
    </a>
    <span class="nav-crisis-item nav-disabled">🔥 Incendie</span>
    <span class="nav-crisis-item nav-disabled">🏔️ Séisme</span>
    <span class="nav-crisis-item nav-disabled">🌪️ Tempête</span>
    <span class="nav-crisis-item nav-disabled">🏜️ Sécheresse</span>
  </div>
  <div class="nav-right">
    <div class="nav-status">
      <div class="nav-status-dot"></div>
      S1 OPÉRATIONNEL
    </div>
    <div class="nav-version">v1.0</div>
  </div>
</nav>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# HEADER MODULE
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<div class="module-header">
  <div class="module-header-left">
    <div class="module-icon">🌊</div>
    <div class="module-title">
      <h2>MODULE INONDATION</h2>
      <p>Cartographie SAR automatisée · Sentinel-1 GRD · SNAP + QGIS/GDAL</p>
    </div>
  </div>
  <div class="module-nav">
    <a href="/" target="_self">← Retour CCIP</a>
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR — Formulaire
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🛰️ Nouveau traitement")

    mode = st.radio(
        "Mode de détection",
        ["🌊  Image unique (TP2)", "📡  Avant / Après (TP1)"],
        key="mode"
    )
    is_diff = "Avant" in mode

    st.markdown("---")
    st.markdown("**Images Sentinel-1**")

    uf_after = st.file_uploader(
        "Image après inondation \\*",
        type=["zip", "SAFE"],
        key="uf_after",
        help="Fichier Sentinel-1 GRD (.zip ou .SAFE.zip)"
    )
    img_after = save_upload(uf_after) if uf_after else ""

    if is_diff:
        uf_before = st.file_uploader(
            "Image avant inondation \\*",
            type=["zip", "SAFE"],
            key="uf_before",
            help="Fichier Sentinel-1 GRD avant événement"
        )
        img_before = save_upload(uf_before) if uf_before else ""
    else:
        img_before = ""

    # Afficher le nom du fichier chargé
    if img_after:
        st.caption(f"✅ Après : `{os.path.basename(img_after)}`")
    if img_before:
        st.caption(f"✅ Avant : `{os.path.basename(img_before)}`")

    st.markdown("---")
    st.markdown("**Zone d'intérêt**")

    # ── Catalogue régions / provinces du Maroc ──────────────────
    MAROC_ZONES = {
        "── Régions ──": None,
        "Tanger-Tétouan-Al Hoceïma":    (-5.92, 34.78, -5.00, 35.93),
        "Oriental":                      (-2.50, 32.50,  2.30, 35.20),
        "Fès-Meknès":                    (-5.70, 32.80, -3.50, 34.80),
        "Rabat-Salé-Kénitra":            (-6.80, 33.50, -5.90, 34.90),
        "Béni Mellal-Khénifra":          (-6.70, 31.80, -4.60, 33.20),
        "Casablanca-Settat":             (-7.80, 32.20, -6.50, 34.10),
        "Marrakech-Safi":                (-9.80, 30.80, -6.80, 32.80),
        "Drâa-Tafilalet":                (-5.50, 29.50, -3.00, 32.50),
        "Souss-Massa":                   (-9.90, 29.30, -7.50, 31.00),
        "Guelmim-Oued Noun":             (-13.00, 27.70, -7.80, 29.60),
        "Laâyoune-Sakia El Hamra":       (-17.10, 25.80,-12.00, 27.90),
        "Dakhla-Oued Ed-Dahab":          (-17.20, 21.30,-13.80, 25.90),
        "── Provinces ──": None,
        "Kénitra":                       (-6.70, 34.00, -6.00, 34.80),
        "Sidi Kacem":                    (-5.90, 34.00, -5.30, 34.60),
        "Sidi Slimane":                  (-6.10, 34.10, -5.70, 34.50),
        "El Gharb (Sidi Kacem+Kénitra)": (-6.80, 33.50, -4.80, 35.80),
        "Larache":                       (-6.20, 34.80, -5.60, 35.50),
        "Al Hoceïma":                    (-4.20, 34.80, -3.40, 35.60),
        "Nador":                         (-3.50, 34.60, -1.90, 35.40),
        "Berkane":                       (-2.50, 34.70, -1.60, 35.20),
        "Oujda-Angad":                   (-2.10, 34.40, -0.90, 35.00),
        "Fès":                           (-5.20, 33.70, -4.70, 34.20),
        "Meknès":                        (-5.70, 33.50, -5.30, 34.00),
        "Taounate":                      (-4.90, 34.30, -4.10, 35.00),
        "Taza":                          (-4.60, 33.90, -3.60, 34.80),
        "Rabat":                         (-6.90, 33.85, -6.60, 34.20),
        "Salé":                          (-6.90, 33.95, -6.60, 34.20),
        "Khouribga":                     (-6.90, 32.60, -6.30, 33.20),
        "Beni Mellal":                   (-6.50, 32.00, -6.00, 32.50),
        "Azilal":                        (-6.80, 31.50, -6.20, 32.30),
        "Casablanca":                    (-7.70, 33.40, -7.30, 33.80),
        "Settat":                        (-7.60, 32.80, -7.00, 33.40),
        "Marrakech":                     (-8.20, 31.40, -7.80, 31.80),
        "El Haouz":                      (-8.60, 30.80, -7.70, 31.50),
        "Essaouira":                     (-9.80, 31.00, -9.00, 31.80),
        "Safi":                          (-9.40, 31.90, -8.80, 32.50),
        "Ouarzazate":                    (-7.00, 30.20, -6.00, 31.00),
        "Zagora":                        (-5.90, 29.50, -4.80, 30.50),
        "Agadir-Ida-Ou-Tanane":          (-9.80, 30.10, -9.00, 30.60),
        "Tiznit":                        (-9.80, 29.40, -8.90, 30.10),
        "Taroudant":                     (-9.20, 30.00, -7.50, 30.80),
        "── Saisie manuelle ──": None,
    }

    zone_names = list(MAROC_ZONES.keys())
    selected_zone = st.selectbox(
        "Région / Province",
        zone_names,
        index=zone_names.index("El Gharb (Sidi Kacem+Kénitra)"),
        key="selected_zone"
    )

    # Récupérer les coordonnées de la zone sélectionnée
    zone_coords = MAROC_ZONES.get(selected_zone)
    if zone_coords:
        _lon_min, _lat_min, _lon_max, _lat_max = zone_coords
    else:
        _lon_min, _lat_min, _lon_max, _lat_max = -6.8, 33.5, -4.8, 35.8

    # Champs modifiables (pré-remplis selon la zone)
    c1, c2 = st.columns(2)
    with c1:
        lon_min = st.number_input("Lon Min", value=float(_lon_min), step=0.1, format="%.2f", key="lon_min")
        lat_min = st.number_input("Lat Min", value=float(_lat_min), step=0.1, format="%.2f", key="lat_min")
    with c2:
        lon_max = st.number_input("Lon Max", value=float(_lon_max), step=0.1, format="%.2f", key="lon_max")
        lat_max = st.number_input("Lat Max", value=float(_lat_max), step=0.1, format="%.2f", key="lat_max")

    # Détection automatique de la zone UTM
    lon_center = (lon_min + lon_max) / 2
    if lon_center < -6.0:
        auto_epsg = 32629   # UTM 29N — Maroc Ouest
        utm_label = "UTM 29N"
    else:
        auto_epsg = 32630   # UTM 30N — Maroc Est / Oriental
        utm_label = "UTM 30N"
    st.caption(f"Projection détectée : **EPSG:{auto_epsg}** ({utm_label})")

    with st.expander("⚙️ Paramètres avancés"):
        pol      = st.selectbox("Polarisation", ["VH", "VV"])
        seuil_db = st.slider("Seuil absolu TP2 (dB)", -40, -10, -26)
        st.caption("TP2 — Eau typique : -30 à -20 dB")
        seuil_diff_db = st.slider("Seuil différentiel TP1 (dB)", 1, 10, 3)
        st.caption("TP1 — Différence avant−après : 3 dB standard SAR")
        px       = st.selectbox("Résolution (m)", [10, 20, 30])
        dem      = st.selectbox("DEM", ["SRTM 1Sec HGT", "SRTM 3Sec", "Copernicus 30m Global DEM"])
        area_min = st.number_input("Surface min polygone (ha)", value=0.5, min_value=0.1, step=0.1)
        communes_shp = st.text_input("Couche communes (optionnel)", placeholder="/chemin/communes.shp")

    st.markdown("---")

    # Visualisation du pipeline
    steps_tp2 = [
        ("1","Apply Orbit File","Orbites précises"),
        ("2","Thermal Noise Removal","Bruit thermique"),
        ("3","Calibration","Sigma0 VH"),
        ("4","Speckle Filter","Refined Lee 7×7"),
        ("5","Terrain Correction","SRTM, 10m, UTM 29N"),
        ("6","Linear → dB","Conversion log"),
        ("7","Seuillage BandMaths",f"< {-26 if 'seuil_db' not in st.session_state else st.session_state.get('seuil_db',-26)} dB"),
        ("8","Vectorisation","gdal_polygonize"),
        ("9","Statistiques","Par commune/province"),
    ]
    steps_tp1 = [("★","TP1","Idem + différence avant/après")] + steps_tp2[:-3]

    with st.expander("📋 Pipeline de traitement", expanded=False):
        for num, lbl, detail in (steps_tp1 if is_diff else steps_tp2):
            st.markdown(f"""
            <div class="pipeline-step">
              <div class="step-num">{num}</div>
              <div class="step-label">{lbl}</div>
              <div class="step-detail">{detail}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")
    btn_launch = st.button("🚀  LANCER LE TRAITEMENT", type="primary", use_container_width=True)

    if btn_launch:
        if not img_after:
            st.error("Image après inondation obligatoire — veuillez uploader un fichier")
        elif is_diff and not img_before:
            st.error("Image avant inondation obligatoire — veuillez uploader un fichier")
        else:
            params = {
                "image_after":   img_after,
                "polarisation":  pol,
                "seuil_db":       float(seuil_db),
                "seuil_diff_db":  float(seuil_diff_db),
                "pixel_spacing": float(px),
                "dem":           dem,
                "area_min_ha":   float(area_min),
                "epsg":          auto_epsg,
                "aoi": {
                    "lon_min": lon_min, "lat_min": lat_min,
                    "lon_max": lon_max, "lat_max": lat_max,
                },
            }
            if is_diff and img_before:
                params["image_before"] = img_before
            if communes_shp.strip():
                params["communes_shp"] = communes_shp.strip()

            jid = launch_job(params)
            st.session_state["active_job"] = jid
            st.session_state.pop("view_job", None)
            load_jobs.clear()
            st.rerun()

# ═══════════════════════════════════════════════════════════════
# ONGLETS
# ═══════════════════════════════════════════════════════════════
tab_active, tab_results, tab_history, tab_doc = st.tabs([
    "⏳  Traitement actif",
    "📊  Résultats",
    "🗂️  Historique",
    "📖  Documentation",
])

# ─── TAB 1 : Traitement actif ─────────────────────────────────
with tab_active:
    active_jid = st.session_state.get("active_job")

    if not active_jid:
        # Vérifier s'il y a un job en cours
        running = [j for j in JOBS.values() if j.status == "running"]
        if running:
            st.info(f"Job en cours détecté : `{running[0].id}`")
            if st.button("Reprendre le suivi"):
                st.session_state["active_job"] = running[0].id
                st.rerun()
        else:
            st.markdown("""
            <div style="text-align:center;padding:60px 20px;color:#37474f">
              <div style="font-size:3em;margin-bottom:16px">🛰️</div>
              <div style="font-size:1.1em;color:#546e7a">Aucun traitement en cours</div>
              <div style="font-size:.85em;margin-top:8px">
                Configurez vos images Sentinel-1 dans le panneau gauche<br>
                puis cliquez sur <b style="color:#64b5f6">LANCER LE TRAITEMENT</b>
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        job = reload_job(active_jid)
        if not job:
            st.error("Job introuvable"); st.stop()

        # En-tête
        h1, h2, h3, h4 = st.columns([4, 1, 1, 1])
        with h1:
            mode_lbl = "Avant/Après (TP1)" if job.params.get("image_before") else "Image unique (TP2)"
            st.markdown(f"**Job** `{job.id}` &nbsp;·&nbsp; {mode_lbl} &nbsp; "
                        + status_badge(job.status), unsafe_allow_html=True)
        with h2:
            if job.status == "running" and st.button("🔄 Actualiser"):
                st.rerun()
        with h3:
            if job.status == "running":
                if st.button("⏹ Arrêter", type="secondary", use_container_width=True):
                    job.status = "cancelled"
                    job.log("Traitement annulé par l'utilisateur", "WARN")
                    job._save_state()
                    st.rerun()
        with h4:
            if st.button("✕ Fermer"):
                st.session_state.pop("active_job", None)
                st.rerun()

        # Progression
        st.progress(job.progress / 100,
                    text=f"{job.progress}% — " + {
                        "done":"✅ Terminé","error":"❌ Erreur",
                        "running":"⏳ Traitement en cours…",
                        "cancelled":"⏹ Annulé par l'utilisateur"
                    }.get(job.status, job.status))

        # Logs
        st.markdown("**Journal de traitement**")
        log_html = ""
        for l in job.logs[-80:]:
            cls = {"SNAP":"log-snap","QGIS":"log-qgis","WARN":"log-warn",
                   "ERROR":"log-error"}.get(l.get("level",""), "log-info")
            ts  = l.get("ts","")
            msg = (l.get("msg","") or "").replace("<","&lt;").replace(">","&gt;")
            log_html += f'<div class="{cls}"><span class="log-ts">{ts}</span>{msg}</div>'
        st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

        # Polling
        if job.status == "running":
            time.sleep(2); st.rerun()
        elif job.status == "cancelled":
            st.warning("⏹ Traitement annulé.")
        elif job.status == "done":
            st.success("✅ Traitement terminé avec succès !")
            if st.button("📊 Voir les résultats →", type="primary"):
                st.session_state["view_job"] = job.id
                st.session_state.pop("active_job", None)
                st.rerun()

# ─── TAB 2 : Résultats ───────────────────────────────────────
with tab_results:
    done_jobs = {jid: j for jid, j in JOBS.items() if j.status == "done"}

    if not done_jobs:
        st.info("Aucun traitement terminé.")
    else:
        # Trier par date de création décroissante (dernier ajout en premier)
        sorted_jids = sorted(done_jobs.keys(), key=lambda j: done_jobs[j].created, reverse=True)

        view_jid = st.session_state.get("view_job", sorted_jids[0])
        if view_jid not in done_jobs:
            view_jid = sorted_jids[0]

        selected = st.selectbox(
            "Traitement",
            sorted_jids,
            index=sorted_jids.index(view_jid),
            format_func=lambda j: f"{'🔵 Avant/Après' if done_jobs[j].params.get('image_before') else '⚪ Image unique'}  ·  {fmt_date(done_jobs[j].created)}  ·  {j[:8]}"
        )
        st.session_state["view_job"] = selected
        job = reload_job(selected)

        if job:
            # ── Métriques ────────────────────────────────────
            csv_path = job.results.get("stats_csv", "")
            total_ha, n_communes, n_provinces = 0.0, 0, 0
            df_stats = pd.DataFrame()

            if csv_path and os.path.exists(csv_path):
                try:
                    df_raw = pd.read_csv(csv_path)
                    df_raw.columns = [c.strip() for c in df_raw.columns]
                    df = df_raw[df_raw.iloc[:, 0].astype(str) != "TOTAL"].copy()
                    if "Surface_ZI_ha" in df.columns:
                        df["Surface_ZI_ha"] = pd.to_numeric(df["Surface_ZI_ha"], errors="coerce")
                        df = df.dropna(subset=["Surface_ZI_ha"])
                        total_ha   = df["Surface_ZI_ha"].sum()
                        n_communes = len(df)
                        if "Province" in df.columns:
                            n_provinces = df["Province"].nunique()
                        df_stats = df.sort_values("Surface_ZI_ha", ascending=False).reset_index(drop=True)
                except Exception as e:
                    st.warning(str(e))

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Surface inondée", f"{total_ha:,.0f} ha")
            m2.metric("Superficie", f"{total_ha/100:,.1f} km²")
            m3.metric("Communes", n_communes)
            m4.metric("Provinces", n_provinces)

            st.divider()

            # ── Tableau + filtres ────────────────────────────
            if not df_stats.empty:
                st.markdown("#### Tableau des zones inondées par commune")
                fc1, fc2, fc3 = st.columns([2, 2, 1])
                with fc1:
                    if "Province" in df_stats.columns:
                        provs = ["Toutes"] + sorted(df_stats["Province"].dropna().unique().tolist())
                        prov_filter = st.selectbox("Province", provs)
                    else:
                        prov_filter = "Toutes"
                with fc2:
                    if "Region" in df_stats.columns:
                        regs = ["Toutes"] + sorted(df_stats["Region"].dropna().unique().tolist())
                        reg_filter = st.selectbox("Région", regs)
                    else:
                        reg_filter = "Toutes"
                with fc3:
                    n_show = st.number_input("Lignes", 10, max(10,len(df_stats)), min(50, len(df_stats)), step=10)

                df_view = df_stats.copy()
                if prov_filter != "Toutes" and "Province" in df_view.columns:
                    df_view = df_view[df_view["Province"] == prov_filter]
                if reg_filter != "Toutes" and "Region" in df_view.columns:
                    df_view = df_view[df_view["Region"] == reg_filter]

                cols_show = [c for c in ["Region","Province","Commune","Surface_ZI_ha"] if c in df_view.columns]
                display_df = df_view[cols_show].head(int(n_show)).copy()
                if "Surface_ZI_ha" in display_df.columns:
                    display_df["Surface_ZI_ha"] = display_df["Surface_ZI_ha"].map("{:,.2f}".format)
                st.dataframe(display_df, use_container_width=True, hide_index=True)

                # Graphique provinces
                if "Province" in df_stats.columns and n_provinces > 1:
                    st.markdown("#### Répartition par province (ha)")
                    by_prov = df_stats.groupby("Province")["Surface_ZI_ha"].sum().sort_values(ascending=False)
                    st.bar_chart(by_prov, color="#2196f3")

            st.divider()

            # ── Fichiers produits + téléchargement/visualisation ──
            st.markdown("#### Fichiers produits")

            def _sz(p):
                if not p: return ""
                s = os.path.getsize(p) if os.path.isfile(p) else 0
                return f"{s/1e6:.1f} MB" if s>1e6 else f"{s/1e3:.0f} KB"

            def _tif_to_png_bytes(tif_path):
                """Convertit un GeoTIFF en PNG pour prévisualisation."""
                try:
                    from osgeo import gdal
                    import numpy as np
                    ds = gdal.Open(tif_path)
                    if ds is None: return None
                    nb = ds.RasterCount
                    def _stretch(arr):
                        arr = arr.astype(np.float32)
                        valid = arr[np.isfinite(arr) & (arr > -9000)]
                        if len(valid) == 0: return np.zeros_like(arr, dtype=np.uint8)
                        lo, hi = np.percentile(valid, 2), np.percentile(valid, 98)
                        return np.clip((arr - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
                    if nb >= 3:
                        r = _stretch(ds.GetRasterBand(1).ReadAsArray())
                        g = _stretch(ds.GetRasterBand(2).ReadAsArray())
                        b = _stretch(ds.GetRasterBand(3).ReadAsArray())
                        rgb = np.stack([r, g, b], axis=-1)
                    else:
                        band = ds.GetRasterBand(1).ReadAsArray()
                        gray = _stretch(band)
                        rgb = np.stack([gray, gray, gray], axis=-1)
                    from PIL import Image
                    img = Image.fromarray(rgb)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return buf.getvalue()
                except Exception:
                    return None

            # ── Rapport HTML ──────────────────────────────────
            rap = job.results.get("rapport","")
            if rap and os.path.exists(rap):
                with open(rap,"rb") as f: rap_bytes = f.read()
                rc1, rc2 = st.columns([3,1])
                rc1.markdown(f"**📄 Rapport HTML** · {_sz(rap)}")
                rc2.download_button("📥 Télécharger", rap_bytes,
                    f"rapport_{selected[:8]}.html", "text/html", use_container_width=True,
                    key="dl_rapport")
                with st.expander("👁 Visualiser le rapport", expanded=False):
                    _stc.html(rap_bytes.decode("utf-8","replace"), height=600, scrolling=True)

            st.divider()

            # ── Composition RGB ───────────────────────────────
            rgb_path = job.results.get("rgb","")
            if rgb_path and os.path.exists(rgb_path):
                rc1, rc2 = st.columns([3,1])
                rc1.markdown(f"**🎨 Composition RGB** (R=avant, G=après) · {_sz(rgb_path)}")
                with open(rgb_path,"rb") as f: rgb_bytes = f.read()
                rc2.download_button("📥 Télécharger", rgb_bytes,
                    "RGB_composite.tif", "image/tiff", use_container_width=True, key="dl_rgb")
                with st.expander("👁 Prévisualiser RGB", expanded=True):
                    png = _tif_to_png_bytes(rgb_path)
                    if png:
                        st.image(png, caption="Rouge=avant, Vert/Bleu=après — zones rouges = inondées", use_container_width=True)
                    else:
                        st.info("Prévisualisation indisponible (GDAL/PIL requis)")

            st.divider()

            # ── GeoTIFFs raster ───────────────────────────────
            st.markdown("**🗂 Rasters GeoTIFF**")
            tif_files = [
                ("mask_water", "🗺️ Masque eau binaire", "mask_water.tif"),
                ("before_db",  "📡 Image avant (dB)",   "before_dB.tif"),
                ("after_db",   "📡 Image après (dB)",   "after_dB.tif"),
                ("diff_db",    "📊 Différence amplitude","amplitude_diff_dB.tif"),
            ]
            tif_cols = st.columns(2)
            for i, (key, lbl, fname_dl) in enumerate(tif_files):
                p = job.results.get(key,"")
                col = tif_cols[i % 2]
                if p and os.path.exists(p):
                    col.markdown(f"{lbl} · `{_sz(p)}`")
                    with open(p,"rb") as f: data = f.read()
                    col.download_button(f"📥 {fname_dl}", data, fname_dl,
                        "image/tiff", use_container_width=True, key=f"dl_{key}")
                    with col.expander("👁 Aperçu"):
                        png = _tif_to_png_bytes(p)
                        if png:
                            st.image(png, use_container_width=True)
                        else:
                            st.caption("Aperçu indisponible")

            st.divider()

            # ── Vecteur shapefile ─────────────────────────────
            zi_shp = job.results.get("zones_inondees","")
            if zi_shp and os.path.exists(zi_shp):
                st.markdown("**🔶 Vecteur zones inondées (Shapefile)**")
                shp_dir = os.path.dirname(zi_shp)
                shp_base = os.path.splitext(os.path.basename(zi_shp))[0]
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for ext in [".shp",".shx",".dbf",".prj",".cpg"]:
                        fp = os.path.join(shp_dir, shp_base + ext)
                        if os.path.exists(fp):
                            zf.write(fp, shp_base + ext)
                buf.seek(0)
                sc1, sc2 = st.columns([3,1])
                sc1.markdown(f"Shapefile ZIP — {len(buf.getvalue())//1024} KB")
                sc2.download_button("📥 Shapefile ZIP", buf.getvalue(),
                    f"ZI_inondation_{selected[:8]}.zip", "application/zip",
                    use_container_width=True, key="dl_shp")

            st.divider()

            # ── CSV statistiques ──────────────────────────────
            st.markdown("**📋 Statistiques CSV**")
            dl1, dl2, dl3 = st.columns(3)
            with dl1:
                if csv_path and os.path.exists(csv_path):
                    with open(csv_path,"rb") as f:
                        st.download_button("📥 CSV communes", f.read(),
                            f"stats_{selected[:8]}.csv", "text/csv",
                            use_container_width=True, key="dl_csv")
            with dl2:
                prov_dir = job.results.get("provinces_dir","")
                if prov_dir and os.path.isdir(prov_dir):
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf,"w") as zf:
                        for fn in os.listdir(prov_dir):
                            if fn.endswith(".csv"):
                                zf.write(os.path.join(prov_dir,fn), fn)
                    buf.seek(0)
                    st.download_button("📦 ZIP par province", buf.read(),
                        f"provinces_{selected[:8]}.zip", "application/zip",
                        use_container_width=True, key="dl_prov")
            with dl3:
                # ZIP tout le job
                job_dir = job.outdir if hasattr(job,"outdir") else ""
                if job_dir and os.path.isdir(job_dir):
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
                        for root, _, files in os.walk(job_dir):
                            for fn in files:
                                if not fn.endswith((".tif",".zip")):  # exclure gros fichiers
                                    fp = os.path.join(root, fn)
                                    zf.write(fp, os.path.relpath(fp, job_dir))
                    buf.seek(0)
                    st.download_button("📦 ZIP résultats complets", buf.read(),
                        f"resultats_{selected[:8]}.zip", "application/zip",
                        use_container_width=True, key="dl_all")

# ─── TAB 3 : Historique ──────────────────────────────────────
with tab_history:
    if not JOBS:
        st.info("Aucun traitement dans l'historique.")
    else:
        rows = []
        for jid, j in sorted(JOBS.items(), key=lambda x: x[1].created, reverse=True):
            rows.append({
                "Job ID":   jid,
                "Mode":     "Avant/Après" if j.params.get("image_before") else "Image unique",
                "Statut":   j.status,
                "Progrès":  f"{j.progress}%",
                "Créé":     fmt_date(j.created),
                "Terminé":  fmt_date(j.finished) or "—",
                "Image":    os.path.basename(j.params.get("image_after","")) or "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.divider()

        sorted_all = sorted(JOBS.keys(), key=lambda j: JOBS[j].created, reverse=True)
        sel = st.selectbox(
            "Ouvrir un job",
            sorted_all,
            format_func=lambda j: f"{JOBS[j].status.upper()}  ·  {fmt_date(JOBS[j].created)}  ·  {j[:8]}"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📊 Voir résultats", use_container_width=True):
                st.session_state["view_job"] = sel; st.rerun()
        with c2:
            if st.button("📺 Suivre logs", use_container_width=True):
                st.session_state["active_job"] = sel; st.rerun()

# ─── TAB 4 : Documentation ───────────────────────────────────
with tab_doc:
    st.markdown("""
## Pipeline de traitement automatisé Sentinel-1

### TP1 — Différence d'amplitude (mode Avant/Après)
| # | Étape | Opérateur SNAP | Paramètre |
|---|-------|----------------|-----------|
| 1 | Orbite | Apply Orbit File | Sentinel Precise Auto Download |
| 2 | Bruit | Thermal Noise Removal | VH |
| 3 | Calibration | Calibrate | Sigma0 |
| 4 | Speckle | Speckle-Filter | Refined Lee 7×7 |
| 5 | Géométrie | Terrain-Correction | SRTM 1Sec HGT, 10m |
| 6 | Log | LinearToFromdB | Sigma0 → dB |
| 7 | Différence | QGIS/GDAL | avant − après > seuil → inondé |
| 8 | RGB | gdal | R=avant, G=B=après |

---

### TP2 — Seuillage VH (mode Image unique)
Étapes 1 → 6 identiques à TP1, puis :

| # | Étape | Outil | Résultat |
|---|-------|-------|----------|
| 7 | Seuillage | BandMaths SNAP | `Sigma0_VH_dB < -26 → 1` |
| 8 | Export | GeoTIFF Writer | Masque binaire 10m |

---

### TP3 — Vectorisation + Statistiques (QGIS/GDAL)
| Étape | Outil | Résultat |
|-------|-------|----------|
| A. Lissage | Filtre gaussien σ=2 | Suppression bruit résiduel |
| B. Reclassification | K-means 2 classes | Seuil Natural Breaks auto |
| C. Vectorisation | gdal_polygonize | Shapefile zones inondées |
| D. Intersection | OGR Intersection | Surface par commune (GADM L4) |
| E. Split | groupby Province | CSV par province |

---

### Références
- **Sentinel-1** : Résolution 10m · Polarisation VH · Mode IW GRD
- **DEM** : SRTM 1Sec HGT (30m) — téléchargement automatique ESA
- **Eaux permanentes** : JRC Global Surface Water (occurrence > 90%)
- **Limites admin** : GADM v4.1 Maroc (4 niveaux — 1515 communes)
""")
