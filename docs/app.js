/* Germany Student Atlas - map front end. No build step; plain browser JavaScript. */
(async function () {
  "use strict";

  // One blue ramp, light = low and dark = high, for every metric.
  const RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"];
  const NODATA = "#e9e8e3";
  const STATUS = {
    shortage:   { label: "Labour shortage", color: "#256abf", note: "official shortage score of 2.0 or more" },
    booming:    { label: "Hiring is growing", color: "#0ca30c", note: "open postings rising" },
    stable:     { label: "Stable", color: "#898781", note: "little change" },
    struggling: { label: "Hiring is shrinking", color: "#d03b3b", note: "open postings falling" },
    unknown:    { label: "No data", color: "#c3c2b7", note: "" },
  };

  const load = (name) => fetch("data/" + name).then((r) => {
    if (!r.ok) throw new Error(name + ": " + r.status);
    return r.json();
  });
  let cities, states, sectors, meta, geo;
  try {
    [cities, states, sectors, meta, geo] = await Promise.all(
      ["cities.json", "states.json", "sectors.json", "meta.json", "states.geojson"].map(load));
  } catch (err) {
    document.getElementById("map").textContent = "Could not load the data files: " + err.message;
    return;
  }
  if (meta.sample) document.getElementById("sample-banner").hidden = false;

  const income = meta.student_income_eur;
  const stateName = Object.fromEntries(geo.features.map((f) => [f.properties.id, f.properties.name]));
  const stateRow = Object.fromEntries(states.map((s) => [s.state_id, s]));
  const num = (v) => (v === null || v === undefined || Number.isNaN(v) ? null : v);
  const lang = () => document.querySelector("input[name=lang]:checked").value;
  const jobsOf = (d) => num(lang() === "all" ? d.jobs_total : d["jobs_" + lang()]);

  const fmtInt = (v) => Math.round(v).toLocaleString("en-GB");
  const fmtEur = (v) => "€" + fmtInt(v);
  const fmtPct = (v) => (v * 100).toFixed(0) + "%";
  const fmt1 = (v) => v.toFixed(1);

  // better: +1 means a higher value is better for a student, -1 lower is better.
  const METRICS = {
    score: { label: "Opportunity score", fmt: fmt1, better: 1,
      help: "0–100. Average percentile rank of low rent burden, job density and low competition.",
      get: (d) => num(d.score) },
    rent: { label: "Monthly rent", fmt: fmtEur, better: -1,
      help: "Rent for a room in a shared flat, per month.",
      get: (d) => num(d.rent_monthly) },
    burden: { label: "Rent as share of student income", fmt: fmtPct, better: -1,
      help: "Rent divided by " + fmtEur(income) + ", the gross monthly pay of a 20-hour minimum-wage student job.",
      get: (d) => (num(d.rent_monthly) === null ? null : d.rent_monthly / income) },
    jobs: { label: "Werkstudent postings", fmt: fmtInt, better: 1,
      help: "Open working-student postings near the city. Use the language switch to split them.",
      get: jobsOf },
    density: { label: "Postings per 1,000 students", fmt: fmt1, better: 1,
      help: "Job postings relative to the number of students who could apply.",
      get: (d) => (jobsOf(d) === null || !num(d.students_total) ? null : jobsOf(d) / d.students_total * 1000) },
    intl: { label: "International students", fmt: fmtInt, better: -1,
      help: "Number of students with a foreign nationality.",
      get: (d) => num(d.students_international) },
    intlShare: { label: "International share of students", fmt: fmtPct, better: -1,
      help: "International students as a share of all students.",
      get: (d) => (num(d.students_international) === null || !num(d.students_total) ? null
        : d.students_international / d.students_total) },
    competition: { label: "Intl. students per English posting", fmt: fmtInt, better: -1,
      help: "International students divided by English-language postings (plus one). Lower means less competition.",
      get: (d) => (num(d.students_international) === null || num(d.jobs_en) === null ? null
        : d.students_international / (d.jobs_en + (num(d.other_en) || 0) + 1)) },
  };

  // ---- controls ------------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const metricSel = $("metric"), stateSel = $("state"), maxRent = $("max-rent"), minJobs = $("min-jobs");
  for (const [key, m] of Object.entries(METRICS)) metricSel.add(new Option(m.label, key));
  for (const f of geo.features.slice().sort((a, b) => a.properties.name.localeCompare(b.properties.name)))
    stateSel.add(new Option(f.properties.name, f.properties.id));

  const rents = cities.map((c) => num(c.rent_monthly)).filter((v) => v !== null);
  const rentTop = rents.length ? Math.ceil(Math.max(...rents) / 10) * 10 : 1000;
  maxRent.min = rents.length ? Math.floor(Math.min(...rents) / 10) * 10 : 0;
  maxRent.max = rentTop; maxRent.value = rentTop;
  const jobCounts = cities.map((c) => num(c.jobs_total)).filter((v) => v !== null);
  minJobs.max = jobCounts.length ? Math.ceil(Math.max(...jobCounts) / 5) * 5 : 100;

  // ---- map -----------------------------------------------------------------------------
  const map = L.map("map", { zoomSnap: 0.25, attributionControl: true, minZoom: 5, maxZoom: 10 });
  map.attributionControl.setPrefix(false).addAttribution(
    'Boundaries: <a href="https://github.com/isellsoap/deutschlandGeoJSON">deutschlandGeoJSON</a>');
  const stateLayer = L.geoJSON(geo, { style: { weight: 1, color: "#fcfcfb", fillOpacity: 1 } }).addTo(map);
  map.fitBounds(stateLayer.getBounds(), { padding: [10, 10] });
  const cityLayer = L.layerGroup().addTo(map);
  let heatLayer = null;
  const markers = {};

  function breaks(values) {
    // Quantile class breaks: four cut points for five classes.
    const v = values.filter((x) => x !== null).sort((a, b) => a - b);
    if (v.length < 2) return [];
    const q = (p) => v[Math.min(v.length - 1, Math.floor(p * v.length))];
    return [...new Set([0.2, 0.4, 0.6, 0.8].map(q))];
  }
  const classOf = (v, b) => (v === null ? NODATA : RAMP[Math.min(RAMP.length - 1,
    Math.round(b.filter((x) => v >= x).length * (RAMP.length - 1) / Math.max(1, b.length)))]);

  function stateMetric(id, key) {
    // State values come from the project's cities in that state, re-using the city formulas.
    const s = stateRow[id];
    return s ? METRICS[key].get(s) : null;
  }

  function visible(c) {
    if (stateSel.value && c.state_id !== stateSel.value) return false;
    const rent = num(c.rent_monthly);
    if (+maxRent.value < +maxRent.max && (rent === null || rent > +maxRent.value)) return false;
    const jobs = jobsOf(c);
    if (+minJobs.value > 0 && (jobs === null || jobs < +minJobs.value)) return false;
    return true;
  }

  function row(label, value) { return "<tr><td>" + label + "</td><td>" + value + "</td></tr>"; }
  function show(key, d) { const v = METRICS[key].get(d); return v === null ? "no data" : METRICS[key].fmt(v); }
  function popup(c) {
    const jobs = num(c.jobs_total) === null ? "no data"
      : fmtInt(c.jobs_total) + " (" + fmtInt(c.jobs_en) + " English, " + fmtInt(c.jobs_de) + " German)";
    return "<h3>" + c.city + "</h3><table>"
      + row("State", stateName[c.state_id])
      + row("Opportunity score", show("score", c))
      + row("Monthly rent", show("rent", c))
      + row("Share of student income", show("burden", c))
      + row("Werkstudent postings", jobs)
      + row("Other job boards", num(c.other_total) === null ? "no data" : fmtInt(c.other_total))
      + row("Postings per 1,000 students", show("density", c))
      + row("Students", num(c.students_total) === null ? "no data" : fmtInt(c.students_total))
      + row("International students", show("intl", c) + (METRICS.intlShare.get(c) === null ? "" : " (" + show("intlShare", c) + ")"))
      + row("Intl. students per English posting", show("competition", c))
      + "</table>";
  }

  function render() {
    const key = metricSel.value, m = METRICS[key];
    $("metric-help").textContent = m.help;
    $("max-rent-out").textContent = +maxRent.value >= +maxRent.max ? "any" : fmtEur(+maxRent.value);
    $("min-jobs-out").textContent = minJobs.value;

    // States
    const sb = breaks(geo.features.map((f) => stateMetric(f.properties.id, key)));
    stateLayer.eachLayer((layer) => {
      const id = layer.feature.properties.id, v = stateMetric(id, key);
      const dim = stateSel.value && stateSel.value !== id;
      layer.setStyle({ fillColor: classOf(v, sb), fillOpacity: dim ? 0.25 : 0.55 });
      layer.unbindTooltip().bindTooltip("<strong>" + stateName[id] + "</strong><br>" + m.label + ": "
        + (v === null ? "no data" : m.fmt(v)) + "<br><span style='color:#52514e'>"
        + (stateRow[id] ? stateRow[id].cities + " cities in this project" : "no cities in this project")
        + "</span>", { sticky: true });
    });

    // Cities
    const shown = cities.filter(visible);
    const cb = breaks(cities.map((c) => m.get(c)));
    cityLayer.clearLayers();
    for (const c of shown) {
      const v = m.get(c);
      const students = num(c.students_total);
      const radius = students === null ? 6 : Math.max(5, Math.min(18, Math.sqrt(students) / 18));
      const marker = L.circleMarker([c.lat, c.lon], {
        radius, weight: 2, color: "#fcfcfb", fillColor: classOf(v, cb), fillOpacity: 1,
      }).bindTooltip("<strong>" + c.city + "</strong><br>" + m.label + ": " + (v === null ? "no data" : m.fmt(v)))
        .bindPopup(popup(c));
      marker.addTo(cityLayer);
      markers[c.city] = marker;
    }

    // Heat map of international students
    if (heatLayer) { map.removeLayer(heatLayer); heatLayer = null; }
    if ($("heat").checked) {
      const pts = shown.filter((c) => num(c.students_international) !== null);
      const top = Math.max(1, ...pts.map((c) => c.students_international));
      heatLayer = L.heatLayer(pts.map((c) => [c.lat, c.lon, c.students_international / top]),
        { radius: 45, blur: 35, minOpacity: 0.35, maxZoom: 6 }).addTo(map);
    }

    renderLegend(m, cb);
    renderRanking(key, shown);
  }

  function renderLegend(m, b) {
    const ticks = b.length ? b.map((x) => m.fmt(x)) : [];
    $("legend").innerHTML = "<h2>" + m.label + "</h2>"
      + '<div class="swatches">' + RAMP.map((c) => '<span style="background:' + c + '"></span>').join("") + "</div>"
      + '<div class="ticks"><span>low</span>' + ticks.map((t) => "<span>" + t + "</span>").join("") + "<span>high</span></div>"
      + '<p class="legend-note">' + (m.better > 0 ? "Darker is better for a student." : "Lighter is better for a student.") + "</p>"
      + '<p class="legend-note"><span class="dot" style="background:' + NODATA + ';border:1px solid #c3c2b7"></span>No data'
      + "<br>Circle size shows the number of students. State shading uses only the cities in this project.</p>";
  }

  function renderRanking(key, shown) {
    const m = METRICS[key];
    const rows = shown.map((c) => ({ c, v: m.get(c) })).filter((r) => r.v !== null)
      .sort((a, b) => (b.v - a.v) * m.better);
    const missing = shown.length - rows.length;
    let html = '<p class="count">' + shown.length + " of " + cities.length + " cities match the filters"
      + (missing ? "; " + missing + " have no value for this measure" : "") + ". Best for a student first.</p>";
    if (!rows.length) html += '<p class="empty">Nothing to rank. Loosen the filters or pick another measure.</p>';
    else {
      html += '<table><thead><tr><th>#</th><th class="text">City</th><th>' + m.label + "</th>"
        + (key === "rent" ? "" : "<th>Rent</th>") + "</tr></thead><tbody>";
      rows.forEach((r, i) => {
        html += '<tr class="clickable" data-city="' + r.c.city + '"><td>' + (i + 1) + '</td><td class="text">' + r.c.city
          + "</td><td>" + m.fmt(r.v) + "</td>" + (key === "rent" ? "" : "<td>" + show("rent", r.c) + "</td>") + "</tr>";
      });
      html += "</tbody></table>";
    }
    $("ranking").innerHTML = html;
  }

  $("ranking").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-city]");
    if (!tr) return;
    const marker = markers[tr.dataset.city];
    if (marker) { map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 7.5), { duration: 0.6 }); marker.openPopup(); }
  });

  // ---- sectors -------------------------------------------------------------------------
  function renderSectors() {
    if (!sectors.length) {
      $("sectors").innerHTML = '<p class="empty">No sector data yet. It is collected when the pipeline runs online.</p>';
      return;
    }
    const pct = (v) => (num(v) === null ? "–" : (v > 0 ? "+" : "") + (v * 100).toFixed(0) + "%");
    let html = '<p class="count">Open postings on the federal job board by occupational field.</p>';
    for (const key of ["shortage", "booming", "stable", "struggling", "unknown"]) {
      const group = sectors.filter((s) => s.status === key).sort((a, b) => (b.stock || 0) - (a.stock || 0));
      if (!group.length) continue;
      const st = STATUS[key];
      html += '<h2 class="group"><span class="dot" style="background:' + st.color + '"></span>' + st.label
        + ' <span class="chip">' + group.length + "</span></h2>"
        + '<table><thead><tr><th class="text">Field</th><th>Open</th><th>New, 30 d</th><th>Change</th><th>Shortage</th></tr></thead><tbody>';
      for (const s of group) {
        html += '<tr><td class="text">' + s.label_en + "</td><td>" + (num(s.stock) === null ? "–" : fmtInt(s.stock))
          + "</td><td>" + pct(s.fresh_share).replace("+", "") + "</td><td>" + pct(s.stock_change)
          + "</td><td>" + (num(s.shortage_score) === null ? "–" : s.shortage_score.toFixed(1)) + "</td></tr>";
      }
      html += "</tbody></table>";
    }
    html += '<p class="help">“Change” compares open postings with a snapshot at least three weeks older; until two '
      + "snapshots exist, sectors are grouped by the share of postings that are new. “Shortage” is the federal "
      + "employment agency’s score (0–3; 2.0 or more counts as a shortage occupation) when supplied. "
      + "Falling postings signal weaker hiring, not confirmed layoffs.</p>";
    $("sectors").innerHTML = html;
  }

  // ---- data provenance -----------------------------------------------------------------
  function renderAbout() {
    const names = { rents: "Rents", students: "Students", jobs: "Werkstudent postings",
      jobs_other: "Other job boards", listings: "Rental listings", sectors: "Sectors" };
    const words = { live: "fetched", manual: "official figures", sample: "synthetic", missing: "missing", error: "failed" };
    let html = '<p class="count">Built ' + new Date(meta.generated_at).toLocaleString("en-GB") + ".</p><dl>";
    for (const [key, layer] of Object.entries(meta.layers)) {
      html += "<dt>" + (names[key] || key) + ' <span class="chip ' + layer.status + '">' + (words[layer.status] || layer.status)
        + "</span></dt><dd>" + (layer.detail || "") + (layer.period ? " (" + layer.period + ")" : "") + "</dd>";
    }
    html += "</dl><p class=\"help\">Student income assumes " + meta.assumptions.hours_per_week + " hours a week at €"
      + meta.assumptions.hourly_wage_eur.toFixed(2) + " an hour. Methods and limits are in the repository README.</p>";
    $("about").innerHTML = html;
  }

  // ---- wiring --------------------------------------------------------------------------
  for (const el of [metricSel, stateSel, maxRent, minJobs, $("heat")]) el.addEventListener("input", render);
  document.querySelectorAll("input[name=lang]").forEach((el) => el.addEventListener("change", render));
  $("reset").addEventListener("click", () => {
    stateSel.value = ""; maxRent.value = maxRent.max; minJobs.value = 0; $("heat").checked = false;
    document.querySelector("input[name=lang][value=all]").checked = true;
    map.fitBounds(stateLayer.getBounds(), { padding: [10, 10] });
    render();
  });
  stateSel.addEventListener("change", () => {
    stateLayer.eachLayer((l) => { if (l.feature.properties.id === stateSel.value) map.fitBounds(l.getBounds(), { padding: [20, 20] }); });
    if (!stateSel.value) map.fitBounds(stateLayer.getBounds(), { padding: [10, 10] });
  });
  document.querySelectorAll(".tabs button").forEach((btn) => btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b === btn));
    document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== btn.dataset.tab; });
  }));

  renderSectors(); renderAbout(); render();
})();
