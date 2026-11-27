(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";

  const form = $("build-form");
  const submit = $("submit");
  const statusCard = $("status");
  const resultCard = $("result");
  const errorCard = $("error");
  const progress = statusCard.querySelector(".ruler");
  const bar = $("bar");

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

  function project(lat, lng) {
    const x = ((lng + 180) / 360) * 960;
    const y = ((84 - lat) / 142) * 470;
    return [Math.min(960, Math.max(0, x)), Math.min(470, Math.max(0, y))];
  }

  function setError(message) {
    clearTimeout(pollTimer);
    statusCard.hidden = true;
    resultCard.hidden = true;
    errorCard.hidden = false;
    $("error-message").textContent = message;
    submit.disabled = false;
    submit.textContent = "Build map";
    errorCard.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function resetUI() {
    clearTimeout(pollTimer);
    currentJob = null;
    errorCard.hidden = true;
    resultCard.hidden = true;
    statusCard.hidden = true;
    bar.style.transform = "";
    progress.classList.remove("indeterminate");
    progress.setAttribute("aria-valuenow", "0");
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
    $("status-time").textContent =
      elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;

    if (job.total > 0 && job.current >= 0 && stage !== "selecting") {
      const pct = Math.min(100, Math.round((job.current / job.total) * 100));
      progress.classList.remove("indeterminate");
      bar.style.transform = `scaleX(${pct / 100})`;
      $("status-pct").textContent = `${pct}%`;
      progress.setAttribute("aria-valuenow", String(pct));
    } else {
      progress.classList.add("indeterminate");
      bar.style.transform = "";
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

  function renderCountries(countries) {
    const list = $("country-list");
    list.replaceChildren();
    const entries = Object.entries(countries || {}).sort((a, b) => b[1] - a[1]);
    $("country-count").textContent = entries.length
      ? `${fmtNumber(entries.length)} ${entries.length === 1 ? "country" : "countries"}`
      : "";

    if (!entries.length) {
      const empty = document.createElement("p");
      empty.className = "country-more";
      empty.textContent = "No country data in this build";
      list.append(empty);
      return;
    }

    const max = Math.max(...entries.map((entry) => entry[1]), 1);

    entries.slice(0, 8).forEach(([code, count], index) => {
      const row = document.createElement("div");
      row.className = "country-row";

      const label = document.createElement("span");
      label.className = "cc mono";
      label.textContent = code === "??" ? "—" : code;

      const track = document.createElement("span");
      track.className = "country-track";
      const fill = document.createElement("span");
      fill.className = index === 0 ? "country-fill lead" : "country-fill";
      fill.style.transform = `scaleX(${count / max})`;
      track.append(fill);

      const value = document.createElement("span");
      value.className = "count mono";
      value.textContent = fmtNumber(count);

      row.append(label, track, value);
      list.append(row);
    });

    if (entries.length > 8) {
      const more = document.createElement("p");
      more.className = "country-more";
      more.textContent = `and ${entries.length - 8} more`;
      list.append(more);
    }
  }

  function renderCoverage(job, summary) {
    const layer = $("coverage-points");
    layer.replaceChildren();
    const points = Array.isArray(job.points) ? job.points : [];

    if (points.length) {
      const fragment = document.createDocumentFragment();
      points.forEach((point) => {
        const lat = Number(point[0]);
        const lng = Number(point[1]);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
        const [x, y] = project(lat, lng);
        const dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("cx", x.toFixed(1));
        dot.setAttribute("cy", y.toFixed(1));
        dot.setAttribute("r", point[2] ? "3.4" : "3.2");
        dot.setAttribute("class", point[2] ? "pt pt-third" : "pt");
        fragment.append(dot);
      });
      layer.append(fragment);
    }

    $("coverage-meta").textContent = `${fmtNumber(summary.produced)} picks`;
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

    const badge = $("result-badge");
    const complete = summary.produced >= summary.requested;
    badge.textContent = complete ? "Complete" : "Partial";
    badge.dataset.state = complete ? "complete" : "partial";

    $("stat-locations").textContent = fmtNumber(summary.produced);
    $("stat-places").textContent = `${fmtNumber(summary.places_covered)} / ${fmtNumber(summary.places_total)}`;
    $("stat-countries").textContent = fmtNumber(Object.keys(countries).length);
    $("stat-photospheres").textContent = fmtNumber(summary.third_party);

    renderCoverage(job, summary);
    renderCountries(countries);

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
      country.className = "mono";
      country.textContent = row.country || "—";

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
      button.textContent = "Copied";
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

  console.log(
    "%c been2guessr %c built by DCLN · github.com/RealDCLN ",
    "background:#d8a24a;color:#1a1206;font-weight:600;padding:3px 8px;border-radius:4px",
    "color:#aab4aa"
  );
})();
