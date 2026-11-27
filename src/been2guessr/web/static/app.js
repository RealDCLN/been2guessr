(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const form = $("build-form");
  const submit = $("submit");
  const statusCard = $("status");
  const resultCard = $("result");
  const errorCard = $("error");

  const stageTitles = {
    queued: "Waiting for a worker…",
    places: "Scanning your places…",
    panoramas: "Reading panorama metadata…",
    selecting: "Choosing a varied set…",
    done: "Your map is ready",
  };

  let pollTimer = null;
  let startedAt = 0;
  let currentJob = null;

  function fmtNumber(value) {
    return new Intl.NumberFormat().format(value || 0);
  }

  function flagEmoji(code) {
    if (!code || code.length !== 2 || code === "??") return "🌐";
    const base = 0x1f1e6;
    const chars = [...code.toUpperCase()].map((c) => base + (c.charCodeAt(0) - 65));
    return String.fromCodePoint(...chars);
  }

  function setError(message) {
    clearTimeout(pollTimer);
    statusCard.hidden = true;
    resultCard.hidden = true;
    errorCard.hidden = false;
    $("error-message").textContent = message;
    submit.disabled = false;
    submit.textContent = "Build my map";
    window.scrollTo({ top: errorCard.offsetTop - 40, behavior: "smooth" });
  }

  function resetUI() {
    clearTimeout(pollTimer);
    currentJob = null;
    errorCard.hidden = true;
    resultCard.hidden = true;
    statusCard.hidden = true;
    $("bar").style.width = "0%";
    $("bar").parentElement.classList.remove("indeterminate");
    $("bar").parentElement.setAttribute("aria-valuenow", "0");
    $("status-pct").textContent = "0%";
    $("status-time").textContent = "0s";
    $("status-title").textContent = "Finding your places…";
    $("status-message").textContent = "Contacting BeenEverywhere…";
  }

  function readOptions() {
    return {
      source: $("source").value.trim(),
      count: Number($("count").value || 300),
      max_radius_m: Number($("max_radius").value || 1600),
      min_spacing_m: Number($("min_spacing").value || 100),
      per_place_max: Number($("per_place_max").value || 8),
      include_photospheres: $("include_photospheres").checked,
      official_only: $("official_only").checked,
      seed: $("seed").value === "" ? null : Number($("seed").value),
    };
  }

  async function parseError(response) {
    try {
      const body = await response.json();
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) {
        return body.detail.map((item) => item.msg || String(item)).join("; ");
      }
    } catch (_) {
      /* ignore */
    }
    return `Request failed with HTTP ${response.status}.`;
  }

  async function startBuild(event) {
    event.preventDefault();
    const options = readOptions();
    if (!options.source) {
      $("source").focus();
      return;
    }
    if (!Number.isFinite(options.count) || options.count < 1) {
      setError("Choose at least one location.");
      return;
    }

    resetUI();
    submit.disabled = true;
    submit.textContent = "Building…";
    startedAt = Date.now();
    statusCard.hidden = false;
    statusCard.scrollIntoView({ behavior: "smooth", block: "center" });

    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(options),
      });
      if (!response.ok) {
        setError(await parseError(response));
        return;
      }
      const job = await response.json();
      currentJob = job.id;
      poll(job.id);
    } catch (err) {
      setError("Could not reach the server. Is it running?");
    }
  }

  function renderProgress(job) {
    const stage = job.stage || "queued";
    const title = stageTitles[stage] || "Working…";
    $("status-title").textContent = title;
    $("status-eyebrow").textContent = stage === "queued" ? "Queued" : "Working";
    $("status-message").textContent = job.message || "";

    const elapsed = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
    $("status-time").textContent = elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;

    const progress = statusCard.querySelector(".progress");
    const bar = $("bar");
    if (job.total > 0 && job.current >= 0 && stage !== "selecting") {
      const pct = Math.min(100, Math.round((job.current / job.total) * 100));
      progress.classList.remove("indeterminate");
      bar.style.width = `${pct}%`;
      $("status-pct").textContent = `${pct}%`;
      progress.setAttribute("aria-valuenow", String(pct));
    } else {
      progress.classList.add("indeterminate");
      $("status-pct").textContent = "…";
      progress.removeAttribute("aria-valuenow");
    }
  }

  async function poll(jobId) {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
      if (!response.ok) {
        setError(await parseError(response));
        return;
      }
      const job = await response.json();
      if (job.status === "error") {
        setError(job.error || "The build failed.");
        return;
      }
      if (job.status === "done") {
        renderProgress(job);
        renderResult(job);
        return;
      }
      renderProgress(job);
      pollTimer = setTimeout(() => poll(jobId), 1200);
    } catch (err) {
      pollTimer = setTimeout(() => poll(jobId), 2500);
    }
  }

  function renderResult(job) {
    const summary = job.summary || {};
    const countries = summary.countries || {};

    statusCard.hidden = true;
    errorCard.hidden = true;
    resultCard.hidden = false;

    $("result-title").textContent = summary.username
      ? `@${summary.username} · ${fmtNumber(summary.produced)} locations`
      : `${fmtNumber(summary.produced)} locations`;
    $("result-badge").textContent = summary.produced >= summary.requested ? "Complete" : "Partial";
    $("stat-locations").textContent = fmtNumber(summary.produced);
    $("stat-places").textContent = `${fmtNumber(summary.places_covered)} / ${fmtNumber(summary.places_total)}`;
    $("stat-countries").textContent = fmtNumber(Object.keys(countries).length);
    $("stat-photospheres").textContent = fmtNumber(summary.third_party);

    const chips = $("country-chips");
    chips.replaceChildren();
    Object.entries(countries).forEach(([code, count]) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      const flag = document.createElement("span");
      flag.textContent = flagEmoji(code);
      const label = document.createElement("b");
      label.textContent = code === "??" ? "Unknown" : code;
      const num = document.createElement("span");
      num.textContent = fmtNumber(count);
      chip.append(flag, label, num);
      chips.append(chip);
    });

    const warnings = $("warnings");
    warnings.replaceChildren();
    (summary.warnings || []).forEach((text) => {
      const p = document.createElement("p");
      p.className = "warning";
      p.textContent = text;
      warnings.append(p);
    });

    $("download-json").href = job.download;
    $("download-csv").href = job.report;

    const body = $("preview-body");
    body.replaceChildren();
    (job.preview || []).forEach((row) => {
      const tr = document.createElement("tr");
      const place = document.createElement("td");
      place.textContent = row.place || "—";
      const country = document.createElement("td");
      country.textContent = `${flagEmoji(row.country)} ${row.country || "—"}`;
      const coords = document.createElement("td");
      coords.className = "mono";
      coords.textContent = `${row.lat.toFixed(4)}, ${row.lng.toFixed(4)}`;
      const kind = document.createElement("td");
      kind.textContent = row.photosphere ? "Photosphere" : "Official";
      tr.append(place, country, coords, kind);
      body.append(tr);
    });

    submit.disabled = false;
    submit.textContent = "Build another map";
    resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function copyJson() {
    if (!currentJob) return;
    const button = $("copy-json");
    const original = button.textContent;
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(currentJob)}/download.json`);
      if (!response.ok) throw new Error("download failed");
      const text = await response.text();
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied!";
    } catch (_) {
      button.textContent = "Copy failed";
    }
    setTimeout(() => {
      button.textContent = original;
    }, 1800);
  }

  form.addEventListener("submit", startBuild);
  $("retry").addEventListener("click", () => {
    resetUI();
    form.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("copy-json").addEventListener("click", copyJson);
})();
