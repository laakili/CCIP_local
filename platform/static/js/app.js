/* ── État global ────────────────────────────────────────────── */
let currentMode    = "single";
let activeJobId    = null;
let pollInterval   = null;

/* ── Mode toggle ────────────────────────────────────────────── */
function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".toggle-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  document.getElementById("beforeGroup").style.display =
    mode === "diff" ? "block" : "none";
}

/* ── Formulaire → lancer un job ─────────────────────────────── */
document.getElementById("jobForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const btn = document.getElementById("submitBtn");
  btn.disabled = true;
  btn.textContent = "⏳ Lancement…";

  const params = {
    image_after:   document.getElementById("img_after").value.trim(),
    image_before:  currentMode === "diff"
                   ? document.getElementById("img_before").value.trim()
                   : "",
    polarisation:  document.getElementById("polarisation").value,
    seuil_db:      parseFloat(document.getElementById("seuil_db").value),
    pixel_spacing: parseFloat(document.getElementById("pixel_spacing").value),
    dem:           document.getElementById("dem").value,
    area_min_ha:   parseFloat(document.getElementById("area_min_ha").value),
    communes_shp:  document.getElementById("communes_shp").value.trim(),
    epsg:          32629,
    aoi: {
      lon_min: parseFloat(document.getElementById("lon_min").value),
      lat_min: parseFloat(document.getElementById("lat_min").value),
      lon_max: parseFloat(document.getElementById("lon_max").value),
      lat_max: parseFloat(document.getElementById("lat_max").value),
    }
  };

  // Supprimer les champs vides
  if (!params.image_before) delete params.image_before;
  if (!params.communes_shp)  delete params.communes_shp;

  try {
    const res  = await fetch("/api/jobs/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params)
    });
    const data = await res.json();

    if (!res.ok) {
      alert("Erreur: " + (data.error || "inconnue"));
      return;
    }

    startPolling(data.job_id);
    refreshJobsList();

  } catch (err) {
    alert("Erreur de connexion: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "🚀 Lancer le traitement";
  }
});

/* ── Polling d'un job actif ─────────────────────────────────── */
function startPolling(jobId) {
  if (pollInterval) clearInterval(pollInterval);
  activeJobId = jobId;

  const section = document.getElementById("activeJob");
  section.style.display = "block";
  document.getElementById("jobId").textContent = jobId;
  document.getElementById("logsBox").innerHTML = "";
  document.getElementById("resultButtons").style.display = "none";
  document.getElementById("statsSection").style.display = "none";

  pollInterval = setInterval(() => fetchJobState(jobId), 1500);
  fetchJobState(jobId);
}

async function fetchJobState(jobId) {
  try {
    const res  = await fetch(`/api/job/${jobId}/state`);
    const data = await res.json();
    updateJobUI(data);
  } catch (err) {
    console.warn("Poll error:", err);
  }
}

function updateJobUI(job) {
  // Barre de progression
  const pct = job.progress || 0;
  document.getElementById("progressBar").style.width   = pct + "%";
  document.getElementById("progressLabel").textContent =
    pct + "% — " + (job.status === "done" ? "Terminé ✓" :
                    job.status === "error" ? "Erreur ✗" :
                    job.status === "running" ? "En traitement…" : job.status);

  // Logs
  const box = document.getElementById("logsBox");
  box.innerHTML = (job.logs || []).slice(-60).map(l => {
    const cls = l.level === "ERROR" ? "log-error"
              : l.level === "SNAP"  ? "log-snap"
              : l.level === "QGIS"  ? "log-qgis"
              : l.level === "WARN"  ? "log-warn"
              : "log-info";
    return `<div class="${cls}"><span class="log-ts">${l.ts}</span>${escHtml(l.msg)}</div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;

  // Fin du job
  if (job.status === "done" || job.status === "error") {
    clearInterval(pollInterval);
    pollInterval = null;
    refreshJobsList();

    if (job.status === "done") {
      // Boutons de résultats
      const btnRap = document.getElementById("btnRapport");
      const btnCSV = document.getElementById("btnCSV");
      btnRap.href = `/api/job/${job.id}/rapport`;
      btnCSV.href = `/api/job/${job.id}/download`;
      document.getElementById("resultButtons").style.display = "flex";

      // Stats rapides
      showStats(job);
    }
  }
}

function showStats(job) {
  const section = document.getElementById("statsSection");
  const grid    = document.getElementById("statsGrid");

  // Lire les stats depuis les logs
  const logText = (job.logs || []).map(l => l.msg).join("\n");
  const matchHa = logText.match(/Surface totale.*?(\d[\d,]+(?:\.\d+)?)\s*ha/i);
  const matchKm = logText.match(/(\d[\d,]+(?:\.\d+)?)\s*km²/i);
  const matchCom= logText.match(/(\d+)\s*communes/i);
  const matchPol= logText.match(/Polygones.*?(\d+)\s*conserv/i);

  const haVal   = matchHa  ? matchHa[1]  : "—";
  const kmVal   = matchKm  ? matchKm[1]  : "—";
  const comVal  = matchCom ? matchCom[1] : "—";
  const polVal  = matchPol ? matchPol[1] : "—";

  grid.innerHTML = `
    <div class="stat-card"><div class="val">${haVal}</div><div class="lbl">ha inondés</div></div>
    <div class="stat-card"><div class="val">${kmVal}</div><div class="lbl">km² affectés</div></div>
    <div class="stat-card"><div class="val">${comVal}</div><div class="lbl">communes</div></div>
    <div class="stat-card"><div class="val">${polVal}</div><div class="lbl">polygones</div></div>
  `;
  section.style.display = "block";
}

/* ── Liste des jobs ─────────────────────────────────────────── */
async function refreshJobsList() {
  const res  = await fetch("/api/jobs");
  const jobs = await res.json();
  const box  = document.getElementById("jobsList");

  if (!jobs.length) {
    box.innerHTML = "<div class='empty-state'>Aucun traitement lancé</div>";
    return;
  }

  box.innerHTML = jobs.map(j => `
    <div class="job-card" onclick="startPolling('${j.id}')">
      <div class="jc-left">
        <div class="jc-id">${j.id}</div>
        <div class="jc-info">
          📡 ${j.mode} &nbsp;|&nbsp; 🕐 ${fmtDate(j.created)}
          ${j.finished ? " → " + fmtDate(j.finished) : ""}
        </div>
      </div>
      <div class="jc-right">
        <span class="status-badge status-${j.status}">${labelStatus(j.status)}</span>
        <div class="mini-bar-wrap">
          <div class="mini-bar" style="width:${j.progress}%"></div>
        </div>
      </div>
    </div>
  `).join("");
}

/* ── Utilitaires ────────────────────────────────────────────── */
function labelStatus(s) {
  return { pending:"En attente", running:"En cours…", done:"✓ Terminé",
           error:"✗ Erreur", cancelled:"Annulé" }[s] || s;
}

function fmtDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("fr-FR", { hour:"2-digit", minute:"2-digit" });
  } catch { return iso; }
}

function escHtml(str) {
  return (str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

/* ── Démarrage ──────────────────────────────────────────────── */
refreshJobsList();
setInterval(refreshJobsList, 5000);
