/* Verkada Co-Term Planner — frontend logic.
 *
 * No build step, no framework. State lives in a plain array of "column"
 * objects (`state.columns`), each rendered into a card by `renderColumns()`.
 * The catalog is fetched once from /api/catalog and used to populate the
 * "Add license column" picker; column cards themselves are always built
 * dynamically from JS, never hardcoded in the HTML.
 */
(function () {
  "use strict";

  const state = {
    catalog: { families: [], units: [] },
    columns: [], // { id, key, label, family, unit_basis, devices_per_license, term_options_days, skus, claimed_before, active_before }
    newLicenses: [], // { id, columnId, term_days, kind, devices_claimed }
    nextId: 1,
    nextLicenseId: 1,
    pendingNewLicenseColumnId: null, // column to pre-select after "+ Add product" creates one
    chart: null,
  };

  const FAMILY_COLORS = {
    "Cameras": "#4f8cff",
    "Access Control": "#34c77b",
    "Alarms": "#ef5a5a",
    "Environmental Sensors": "#f5a623",
    "Gateway": "#a56eff",
    "Intercom": "#22c1d6",
    "Workplace": "#e0c341",
    "Custom": "#8b93a1",
  };

  function familyColor(family) {
    return FAMILY_COLORS[family] || "#8b93a1";
  }

  function el(tag, opts) {
    opts = opts || {};
    const node = document.createElement(tag);
    if (opts.className) node.className = opts.className;
    if (opts.text !== undefined) node.textContent = opts.text;
    if (opts.html !== undefined) node.innerHTML = opts.html;
    if (opts.attrs) {
      for (const k in opts.attrs) node.setAttribute(k, opts.attrs[k]);
    }
    return node;
  }

  function todayIso() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function slugify(label) {
    return (label || "custom")
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "custom";
  }

  function showError(msg) {
    const banner = document.getElementById("error-banner");
    banner.textContent = msg;
    banner.style.display = msg ? "block" : "none";
  }

  // ---------------------------------------------------------------------
  // Catalog fetch + picker
  // ---------------------------------------------------------------------

  async function loadCatalog() {
    try {
      const resp = await fetch("/api/catalog");
      if (!resp.ok) throw new Error(`catalog fetch failed (${resp.status})`);
      state.catalog = await resp.json();
    } catch (err) {
      showError("Could not load license catalog: " + err.message);
      state.catalog = { families: [], units: [] };
    }
  }

  // Multiple independent "add product" pickers can exist on the page (the
  // Before grid's "+ Add license column" and the New Licenses section's own
  // "+ Add product" trigger). Each is registered with its own button/menu
  // pair and an onPick callback, so New Licenses can register a brand-new
  // product line without going through the Before picker at all.
  const PICKERS = {}; // menuId -> { btnId, onPick }

  function registerPicker(btnId, menuId, onPick) {
    PICKERS[menuId] = { btnId, onPick };
    document.getElementById(btnId).addEventListener("click", (e) => {
      e.stopPropagation();
      togglePicker(menuId);
    });
  }

  function togglePicker(menuId) {
    const menu = document.getElementById(menuId);
    if (menu.style.display === "block") {
      closePicker(menuId);
    } else {
      closeAllPickers();
      openPicker(menuId);
    }
  }

  function openPicker(menuId) {
    const menu = document.getElementById(menuId);
    const onPick = PICKERS[menuId].onPick;
    menu.innerHTML = "";

    const byFamily = {};
    for (const u of state.catalog.units || []) {
      (byFamily[u.family] = byFamily[u.family] || []).push(u);
    }
    const familyOrder = (state.catalog.families || []).filter((f) => byFamily[f]);

    for (const fam of familyOrder) {
      menu.appendChild(el("div", { className: "picker-family", text: fam }));
      for (const u of byFamily[fam]) {
        const item = el("div", { className: "picker-item" });
        item.appendChild(el("div", { className: "pi-label", text: u.label }));
        if (u.unit_basis) {
          item.appendChild(el("div", { className: "pi-basis", text: u.unit_basis }));
        }
        item.addEventListener("click", () => {
          onPick(u);
          closePicker(menuId);
        });
        menu.appendChild(item);
      }
    }

    menu.appendChild(el("hr"));
    const customItem = el("div", {
      className: "picker-item picker-custom",
      text: "+ Add custom column…",
    });
    customItem.addEventListener("click", () => {
      onPick(null);
      closePicker(menuId);
    });
    menu.appendChild(customItem);

    menu.style.display = "block";
  }

  function closePicker(menuId) {
    document.getElementById(menuId).style.display = "none";
  }

  function closeAllPickers() {
    Object.keys(PICKERS).forEach(closePicker);
  }

  document.addEventListener("click", (e) => {
    for (const [menuId, { btnId }] of Object.entries(PICKERS)) {
      const menu = document.getElementById(menuId);
      const btn = document.getElementById(btnId);
      if (!menu.contains(e.target) && e.target !== btn) {
        closePicker(menuId);
      }
    }
  });

  // ---------------------------------------------------------------------
  // Column state
  // ---------------------------------------------------------------------

  function addColumnFromCatalog(catalogUnit) {
    // De-dupe: picking the same catalog product twice (once from the Before
    // picker, once from the New Licenses picker) should reuse one column,
    // not create a duplicate row that would double-count in the breakdown.
    const existing = state.columns.find((c) => c.key === catalogUnit.key);
    if (existing) return existing;

    const col = {
      id: state.nextId++,
      key: catalogUnit.key,
      label: catalogUnit.label,
      family: catalogUnit.family,
      unit_basis: catalogUnit.unit_basis || "",
      devices_per_license: catalogUnit.devices_per_license || 1,
      term_options_days: catalogUnit.term_options_days || [365, 1095, 1825, 3650],
      skus: catalogUnit.skus || [],
      claimed_before: 0,
      active_before: 0,
      custom: false,
    };
    state.columns.push(col);
    renderColumns();
    renderNewLicenses();
    return col;
  }

  function addCustomColumn() {
    const label = window.prompt("Custom license column name:", "");
    if (label === null) return null; // cancelled
    const trimmed = label.trim() || "Custom License";
    const family = window.prompt("Family (group heading):", "Custom") || "Custom";
    const col = {
      id: state.nextId++,
      key: slugify(trimmed) + "_" + state.nextId,
      label: trimmed,
      family: family.trim() || "Custom",
      unit_basis: "",
      devices_per_license: 1,
      term_options_days: [365, 1095, 1825, 3650],
      skus: [],
      claimed_before: 0,
      active_before: 0,
      custom: true,
    };
    state.columns.push(col);
    renderColumns();
    renderNewLicenses();
    return col;
  }

  function removeColumn(id) {
    state.columns = state.columns.filter((c) => c.id !== id);
    state.newLicenses = state.newLicenses.filter((nl) => nl.columnId !== id);
    renderColumns();
    renderNewLicenses();
  }

  function findColumn(id) {
    return state.columns.find((c) => c.id === id);
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------

  function renderColumns() {
    const grid = document.getElementById("columns-grid");
    const emptyState = document.getElementById("empty-state");
    grid.innerHTML = "";

    if (state.columns.length === 0) {
      emptyState.style.display = "block";
      return;
    }
    emptyState.style.display = "none";

    for (const col of state.columns) {
      grid.appendChild(buildColumnCard(col));
    }
  }

  function termLabel(days) {
    const years = Math.round(days / 365);
    return `${years}-Year (${days}d)`;
  }

  function priceHintFor(col, termDays) {
    const sku = (col.skus || []).find((s) => s.term_days === termDays);
    if (!sku) return "";
    return ` — $${sku.us_price.toLocaleString()}`;
  }

  function buildColumnCard(col) {
    const card = el("div", { className: "col-card" });

    // Header
    const head = el("div", { className: "col-head" });
    const titleBlock = el("div");
    titleBlock.appendChild(el("div", { className: "col-title", text: col.label }));
    const tag = el("span", {
      className: "family-tag",
      text: col.family,
      attrs: { style: `background:${familyColor(col.family)};` },
    });
    titleBlock.appendChild(tag);
    head.appendChild(titleBlock);

    const removeBtn = el("button", { className: "danger", text: "×", attrs: { type: "button", title: "Remove column" } });
    removeBtn.addEventListener("click", () => removeColumn(col.id));
    head.appendChild(removeBtn);
    card.appendChild(head);

    if (col.unit_basis) {
      card.appendChild(el("div", { className: "hint", text: col.unit_basis }));
    }

    if (col.custom) {
      card.appendChild(labeledInput("Devices per license", "number", col.devices_per_license, (v) => {
        const n = parseFloat(v);
        col.devices_per_license = isFinite(n) && n > 0 ? n : 1;
      }));
    }

    // "Before" state (shares one org-wide expiration date, set in the header)
    card.appendChild(el("div", { className: "section-label", text: "Before" }));

    const row1 = el("div", { className: "row-2" });
    row1.appendChild(labeledInput("Claimed", "number", col.claimed_before, (v) => {
      col.claimed_before = parseNonNegInt(v);
    }));
    row1.appendChild(labeledInput("Active", "number", col.active_before, (v) => {
      col.active_before = parseNonNegInt(v);
    }));
    card.appendChild(row1);

    return card;
  }

  function labeledInput(labelText, type, value, onChange) {
    const field = el("div", { className: "field" });
    field.appendChild(el("label", { text: labelText }));
    const input = el("input", { attrs: { type } });
    if (type === "number") {
      input.min = "0";
    }
    input.value = value === undefined || value === null ? "" : value;
    input.addEventListener("input", () => onChange(input.value));
    field.appendChild(input);
    return field;
  }

  function parseNonNegInt(v) {
    const n = parseInt(v, 10);
    return isFinite(n) && n >= 0 ? n : 0;
  }

  // ---------------------------------------------------------------------
  // New licenses (shared section: pick product line + term + devices claimed)
  // ---------------------------------------------------------------------

  function renderNewLicenses() {
    const list = document.getElementById("new-licenses-list");
    const form = document.getElementById("new-license-form");
    list.innerHTML = "";
    form.innerHTML = "";

    const KIND_LABEL = { capacity: "Capacity increase", renewal: "Renewal" };

    state.newLicenses.forEach((nl) => {
      const col = findColumn(nl.columnId);
      if (!col) return; // stale entry, column was removed
      const row = el("div", { className: "batch-row" });
      const priceHint = priceHintFor(col, nl.term_days);
      row.appendChild(el("div", {
        className: "batch-info",
        text: `${col.label} — ${KIND_LABEL[nl.kind] || "Capacity increase"} — ${termLabel(nl.term_days)} × ${nl.devices_claimed} device(s)`,
      }));
      if (priceHint) {
        row.appendChild(el("div", { className: "batch-price", text: priceHint.replace(" — ", "") }));
      }
      const rm = el("button", { className: "danger", text: "×", attrs: { type: "button", title: "Remove" } });
      rm.addEventListener("click", () => {
        state.newLicenses = state.newLicenses.filter((x) => x.id !== nl.id);
        renderNewLicenses();
      });
      row.appendChild(rm);
      list.appendChild(row);
    });

    // Add-entry mini form: product line select, term select (depends on
    // product), kind select (capacity increase adds new devices; renewal
    // just extends licensing for devices already claimed), devices input,
    // Add button. Capacity and renewal are independent purchases -- you can
    // add both for the same product line in the same compute, e.g. renewing
    // your existing doors while also adding capacity for 2 new doors.
    //
    // The product list isn't limited to columns already in the Before grid:
    // clicking "+ Add product" above opens the same catalog/custom picker
    // used there, registers the product as a column (with before-state
    // defaulting to 0 claimed/active, editable later), and pre-selects it
    // here -- so a brand-new product line can be purchased without ever
    // touching the Before section.
    if (state.columns.length === 0) {
      list.appendChild(el("div", { className: "hint", text: "No products yet — click \"+ Add product\" above to add one." }));
      return;
    }

    const colSelect = el("select");
    for (const col of state.columns) {
      const opt = el("option", { text: `${col.label} (${col.family})` });
      opt.value = String(col.id);
      colSelect.appendChild(opt);
    }
    if (state.pendingNewLicenseColumnId && state.columns.some((c) => c.id === state.pendingNewLicenseColumnId)) {
      colSelect.value = String(state.pendingNewLicenseColumnId);
    }
    state.pendingNewLicenseColumnId = null;

    const termSelect = el("select");
    function populateTermSelect() {
      const col = findColumn(parseInt(colSelect.value, 10));
      termSelect.innerHTML = "";
      const termOptions = (col && col.term_options_days && col.term_options_days.length)
        ? col.term_options_days
        : [365, 1095, 1825, 3650];
      for (const days of termOptions) {
        const opt = el("option", { text: termLabel(days) + (col ? priceHintFor(col, days) : "") });
        opt.value = String(days);
        termSelect.appendChild(opt);
      }
    }
    populateTermSelect();
    colSelect.addEventListener("change", () => {
      populateTermSelect();
      applyKindDefault();
    });

    const kindSelect = el("select");
    kindSelect.appendChild(el("option", { text: "Capacity increase", attrs: { value: "capacity" } }));
    kindSelect.appendChild(el("option", { text: "Renewal", attrs: { value: "renewal" } }));

    const devicesInput = el("input", { attrs: { type: "number", min: "1", placeholder: "Devices claimed" } });
    devicesInput.value = "";

    function applyKindDefault() {
      const col = findColumn(parseInt(colSelect.value, 10));
      if (kindSelect.value === "renewal" && col && !devicesInput.value) {
        devicesInput.value = col.claimed_before || "";
        devicesInput.placeholder = "Devices covered";
      } else if (kindSelect.value === "capacity") {
        devicesInput.placeholder = "New devices claimed";
      }
    }
    kindSelect.addEventListener("change", () => {
      devicesInput.value = "";
      applyKindDefault();
    });

    const addBtn = el("button", { className: "secondary", text: "Add", attrs: { type: "button" } });
    addBtn.addEventListener("click", () => {
      const columnId = parseInt(colSelect.value, 10);
      const termDays = parseInt(termSelect.value, 10);
      const kind = kindSelect.value === "renewal" ? "renewal" : "capacity";
      const devicesClaimed = parseInt(devicesInput.value, 10);
      if (!columnId || !termDays || !devicesClaimed || devicesClaimed <= 0) return;
      state.newLicenses.push({
        id: state.nextLicenseId++,
        columnId,
        term_days: termDays,
        kind,
        devices_claimed: devicesClaimed,
      });
      renderNewLicenses();
    });

    form.appendChild(colSelect);
    form.appendChild(termSelect);
    form.appendChild(kindSelect);
    form.appendChild(devicesInput);
    form.appendChild(addBtn);
  }

  // ---------------------------------------------------------------------
  // Compute + results rendering
  // ---------------------------------------------------------------------

  function buildRequestPayload(beforeOnly) {
    const orgName = document.getElementById("org-name").value.trim() || "Untitled Org";
    const asOfDate = document.getElementById("as-of-date").value || todayIso();
    const currentExpiration = document.getElementById("current-expiration-date").value || null;

    // Aggregate the flat "new licenses" list (product line + term + kind +
    // devices claimed) into per-column new_claimed_devices / new_batches.
    // Capacity and renewal are independent purchases: a capacity increase
    // claims brand-new devices (adds to the device count AND the license-day
    // pool), while a renewal only extends licensing for devices already
    // claimed (adds license-days only, no device-count change). Both can
    // exist for the same product line in the same compute. Claimed devices
    // are what burn license time, so a batch's license quantity is however
    // many licenses are needed to cover the devices claimed, given that
    // unit's devices_per_license (e.g. 20 users per Mobile NFC license).
    const byColumn = {};
    if (!beforeOnly) {
      for (const nl of state.newLicenses) {
        const col = findColumn(nl.columnId);
        if (!col) continue;
        const bucket = byColumn[nl.columnId] || (byColumn[nl.columnId] = { devices: 0, batches: [] });
        const dpl = col.devices_per_license || 1;
        const qty = Math.max(1, Math.ceil(nl.devices_claimed / dpl));
        bucket.batches.push({ term_days: nl.term_days, quantity: qty });
        if (nl.kind !== "renewal") {
          bucket.devices += nl.devices_claimed;
        }
      }
    }

    const units = state.columns.map((col) => {
      const bucket = byColumn[col.id] || { devices: 0, batches: [] };
      return {
        key: col.key,
        label: col.label,
        family: col.family,
        devices_per_license: col.devices_per_license,
        claimed_before: col.claimed_before,
        active_before: col.active_before,
        expiration_before: currentExpiration,
        new_claimed_devices: bucket.devices,
        new_batches: bucket.batches,
      };
    });

    return { org_name: orgName, as_of_date: asOfDate, units };
  }

  async function postCompute(payload) {
    const resp = await fetch("/api/coterm/compute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data && data.error ? data.error : `Compute failed (${resp.status})`);
    }
    return data;
  }

  async function compute() {
    showError("");

    if (state.columns.length === 0) {
      showError("Add at least one license column before computing.");
      return;
    }

    // Fire two computes against the same engine: the full "after" scenario
    // (with new devices/batches applied) and a "before" scenario with all
    // new additions zeroed out, so we can show a true before/after
    // org-wide co-term comparison using nothing but the documented API.
    let afterData, beforeData;
    try {
      [beforeData, afterData] = await Promise.all([
        postCompute(buildRequestPayload(true)),
        postCompute(buildRequestPayload(false)),
      ]);
    } catch (err) {
      showError(err.message);
      return;
    }

    renderResults(afterData, beforeData);
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    return iso;
  }

  function fmtNum(n, digits) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    });
  }

  function renderResults(afterData, beforeData) {
    document.getElementById("results").style.display = "flex";

    renderCallout(afterData, beforeData);
    renderChart(afterData);
    renderTable(afterData);
  }

  function renderCallout(afterData, beforeData) {
    const callout = document.getElementById("callout");
    callout.innerHTML = "";

    const orgLabel = el("div", { className: "co-term-block" });
    orgLabel.appendChild(el("div", { className: "co-term-label", text: "Org" }));
    orgLabel.appendChild(el("div", { className: "co-term-date", text: afterData.org_name }));
    orgLabel.appendChild(el("div", { className: "co-term-delta", text: `As of ${fmtDate(afterData.as_of_date)}` }));
    callout.appendChild(orgLabel);

    const currentBlock = el("div", { className: "co-term-block" });
    currentBlock.appendChild(el("div", { className: "co-term-label", text: "Current org co-term" }));
    currentBlock.appendChild(el("div", { className: "co-term-date", text: fmtDate(beforeData.org_expiration_date) }));
    currentBlock.appendChild(el("div", { className: "co-term-delta", text: `Runway: ${fmtNum(beforeData.org_remaining_days, 1)} days` }));
    callout.appendChild(currentBlock);

    callout.appendChild(el("div", { className: "arrow", text: "→" }));

    const isLater = afterData.org_remaining_days >= beforeData.org_remaining_days;
    const newBlock = el("div", { className: "co-term-block" });
    newBlock.appendChild(el("div", { className: "co-term-label", text: "New org co-term" }));
    newBlock.appendChild(el("div", {
      className: "co-term-date " + (isLater ? "good" : "bad"),
      text: fmtDate(afterData.org_expiration_date),
    }));
    newBlock.appendChild(el("div", { className: "co-term-delta", text: `Runway: ${fmtNum(afterData.org_remaining_days, 1)} days` }));
    callout.appendChild(newBlock);
  }

  function renderChart(data) {
    const ctx = document.getElementById("breakdown-chart").getContext("2d");
    const rows = data.rows.slice().sort((a, b) => b.total_license_days - a.total_license_days);

    const labels = rows.map((r) => r.label);
    const values = rows.map((r) => r.total_license_days);
    const colors = rows.map((r) => familyColor(r.family));

    if (state.chart) {
      state.chart.destroy();
    }

    state.chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Total license-days",
            data: values,
            backgroundColor: colors,
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const row = rows[ctx.dataIndex];
                return `${fmtNum(row.total_license_days, 0)} days (${fmtNum(row.share_of_org_days_pct, 1)}% of org)`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: "#262c35" },
            ticks: { color: "#8b93a1" },
          },
          y: {
            grid: { display: false },
            ticks: { color: "#e6e9ef" },
          },
        },
      },
    });

    // Resize canvas container height based on number of rows so long
    // lists don't get squished.
    const wrap = document.querySelector(".chart-wrap");
    wrap.style.height = Math.max(260, rows.length * 42) + "px";
  }

  function renderTable(data) {
    const tbody = document.querySelector("#results-table tbody");
    tbody.innerHTML = "";

    for (const row of data.rows) {
      const tr = el("tr");
      tr.appendChild(el("td", { text: row.label }));
      tr.appendChild(el("td", { text: row.family }));
      tr.appendChild(el("td", { text: fmtNum(row.claimed_before) }));
      tr.appendChild(el("td", { text: fmtNum(row.active_before) }));
      tr.appendChild(el("td", { text: fmtDate(row.expiration_before) }));
      tr.appendChild(el("td", { text: fmtNum(row.existing_license_days, 0) }));
      tr.appendChild(el("td", { text: fmtNum(row.added_license_days, 0) }));
      tr.appendChild(el("td", { text: fmtNum(row.total_license_days, 0) }));
      tr.appendChild(el("td", { text: fmtNum(row.required_units_after, 0) }));
      tr.appendChild(el("td", { text: fmtDate(row.standalone_expiration_date) }));
      tr.appendChild(el("td", { text: fmtNum(row.share_of_org_days_pct, 1) + "%" }));
      tbody.appendChild(tr);
    }
  }

  // ---------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------

  function init() {
    document.getElementById("as-of-date").value = todayIso();

    registerPicker("add-column-btn", "picker-menu", (u) => {
      if (u) addColumnFromCatalog(u); else addCustomColumn();
    });
    registerPicker("add-new-license-product-btn", "new-license-picker-menu", (u) => {
      const col = u ? addColumnFromCatalog(u) : addCustomColumn();
      if (col) {
        state.pendingNewLicenseColumnId = col.id;
        renderNewLicenses();
      }
    });

    document.getElementById("compute-btn").addEventListener("click", compute);
    renderColumns();
    renderNewLicenses();
    loadCatalog();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
