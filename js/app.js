// Application State
const state = {
  repos: {}, // Will be loaded from repos.json: {name: [variants]}
  currentRepo: null,
  currentVariant: "clean",
  invertLayers: false,
  loadedCharts: {}, // Cache: {repo-variant: vegaSpec}
};

// DOM Elements
let repoSelect;
let showTagsCheckbox;
let invertCheckbox;
let chartContainer;
let granularitySelect;
let regenerateBtn;
let regenerateStatus;
let dateFrom;
let dateTo;
let showDevelopCheckbox;

// ========================================
// URL State Management
// ========================================

/**
 * Parse URL hash to extract repo and variant
 * Format: #repo-name/variant
 * Example: #human-learn/versioned
 */
function repoNames() {
  return Object.keys(state.repos);
}

function parseURL() {
  const hash = window.location.hash.slice(1); // Remove the '#'
  const names = repoNames();
  const defaultRepo = names[0] || "scikit-lego";

  if (!hash) {
    return {
      repo: defaultRepo,
      variant: "clean",
    };
  }

  const parts = hash.split("/");
  const repo = parts[0] || defaultRepo;
  const variant = parts[1] || "clean";

  // Validate repo exists in loaded repos
  const validRepo = names.includes(repo) ? repo : defaultRepo;

  // Validate variant is available for this repo
  const availableVariants = state.repos[validRepo] || ["clean"];
  const validVariant = availableVariants.includes(variant) ? variant : "clean";

  return {
    repo: validRepo,
    variant: validVariant,
  };
}

/**
 * Update URL hash based on current state
 */
function updateURL() {
  const hash = `#${state.currentRepo}/${state.currentVariant}`;
  if (window.location.hash !== hash) {
    window.history.pushState(null, "", hash);
  }
}

// ========================================
// Chart Loading & Rendering
// ========================================

/**
 * Load chart JSON from file
 */
async function loadChart(repo, variant) {
  const cacheKey = `${repo}-${variant}`;

  // Check cache first
  if (state.loadedCharts[cacheKey]) {
    return state.loadedCharts[cacheKey];
  }

  try {
    const response = await fetch(`charts/${repo}-${variant}.json?t=${Date.now()}`);

    if (!response.ok) {
      throw new Error(`Chart not found: ${response.status}`);
    }

    const spec = await response.json();

    // Cache the loaded chart
    state.loadedCharts[cacheKey] = spec;

    return spec;
  } catch (error) {
    console.error("Error loading chart:", error);
    throw error;
  }
}

/**
 * Render chart using Vega-Embed
 */
/**
 * Apply invert layers transformation to a spec (deep clone to avoid mutating cache)
 */
function applyTransforms(spec) {
  const copy = JSON.parse(JSON.stringify(spec));

  // Collect all encodings (top-level or per-layer)
  const encodings = [];
  if (copy.encoding) encodings.push(copy.encoding);
  if (copy.layer) copy.layer.forEach(l => { if (l.encoding) encodings.push(l.encoding); });

  // Invert layers — apply to ALL encodings
  const sortOrder = state.invertLayers ? "descending" : "ascending";
  encodings.forEach(enc => {
    if (enc.order) enc.order.sort = sortOrder;
  });

  // Date range filter — filter inline data values directly
  const from = dateFrom.value;
  const to = dateTo.value;
  if (from || to) {
    const filterData = (values) => {
      return values.filter(d => {
        // Support both commit_date (chart data) and datetime (tag data)
        const date = d.commit_date || d.datetime;
        if (!date) return true;
        if (from && date < from) return false;
        if (to && date > to + "T23:59:59") return false;
        return true;
      });
    };

    // Filter inline data (values arrays) in each layer or top-level
    if (copy.layer) {
      copy.layer.forEach(l => {
        if (l.data?.values) {
          l.data.values = filterData(l.data.values);
        }
      });
    }

    // Filter datasets (named data)
    if (copy.datasets) {
      for (const key of Object.keys(copy.datasets)) {
        copy.datasets[key] = filterData(copy.datasets[key]);
      }
    }
  }

  return copy;
}

async function renderChart(spec) {
  const embedOpt = {
    mode: "vega-lite",
    actions: {
      export: true, // Enable PNG download
      source: false, // Disable view source
      compiled: false, // Disable view compiled Vega
      editor: false, // Disable open in editor
    },
  };

  try {
    // Clear container
    chartContainer.innerHTML = "";
    chartContainer.className = "";

    // Embed chart
    await vegaEmbed("#chart-container", spec, embedOpt);
  } catch (error) {
    console.error("Error rendering chart:", error);
    throw error;
  }
}

/**
 * Show loading state
 */
function showLoading() {
  chartContainer.className = "loading";
  chartContainer.innerHTML = "<p>Loading chart...</p>";
}

/**
 * Show error message
 */
function showError(repo, variant) {
  chartContainer.className = "error";

  // Get the repo URL from repos.txt for the error message
  const repoUrls = {
    "human-learn": "https://github.com/koaning/human-learn",
    "scikit-lego": "https://github.com/koaning/scikit-lego",
  };

  const repoUrl = repoUrls[repo] || `https://github.com/${repo}`;

  chartContainer.innerHTML = `
        <div class="w-100">
            <h5 class="text-danger">Chart Not Available</h5>
            <p>The <strong>${variant}</strong> chart for <strong>${repo}</strong> couldn't be loaded.</p>
            <p class="mb-2">To generate it, run:</p>
            <code>uv run git_archaeology.py --repo ${repoUrl} --samples 200</code>
        </div>
    `;
}

/**
 * Load and render chart for current state
 */
/**
 * Load develop branch chart if available
 */
async function loadDevelopChart(repo, variant) {
  const devVariant = variant === "versioned" ? "develop-versioned" : "develop-clean";
  try {
    return await loadChart(repo, devVariant);
  } catch {
    return null;
  }
}

/**
 * Merge develop data as a transparent continuation after main.
 * Only shows develop commits that are NEWER than the last main commit
 * (i.e. unreleased work on develop not yet merged to main).
 */
function mergeWithDevelop(mainSpec, devSpec) {
  const main = JSON.parse(JSON.stringify(mainSpec));
  const dev = JSON.parse(JSON.stringify(devSpec));

  // Extract data key — handle both flat specs (data.name) and layered specs (layer[0].data.name)
  const mainDataKey = main.data?.name || (main.layer?.[0]?.data?.name);
  const devDataKey = dev.data?.name || (dev.layer?.[0]?.data?.name);
  if (!devDataKey || !dev.datasets?.[devDataKey]) return main;

  const mainData = main.datasets?.[mainDataKey] || [];
  const devData = dev.datasets[devDataKey] || [];

  // Find the latest commit_date in main
  const mainDates = mainData.map(d => d.commit_date);
  const lastMainDate = mainDates.sort().pop();
  if (!lastMainDate) return main;

  // Filter develop data to only commits AFTER the last main commit
  const devDelta = devData.filter(d => d.commit_date > lastMainDate);
  if (devDelta.length === 0) return main;

  // Rename period → dev_period so Vega-Lite creates a separate legend
  const devDeltaRenamed = devDelta.map(d => ({
    commit_date: d.commit_date,
    line_count: d.line_count,
    dev_period: d.period,
  }));

  // Dev delta layer — viridis with reduced opacity + separate legend
  const devLayer = {
    data: { values: devDeltaRenamed },
    mark: { type: "area", opacity: 0.4 },
    encoding: {
      x: { field: "commit_date", type: "temporal" },
      y: { field: "line_count", type: "quantitative" },
      color: {
        field: "dev_period",
        type: "ordinal",
        scale: { scheme: "viridis" },
        legend: { title: "Dev Period", symbolOpacity: 0.4 },
      },
      order: { field: "dev_period", sort: "ascending" },
    },
  };

  // Build main layers — handle both flat spec (mark+encoding) and layered spec (versioned)
  // Force opacity: 1 on main area to contrast with semi-transparent develop
  const layers = [];
  if (main.layer) {
    main.layer.forEach(l => {
      const copy = JSON.parse(JSON.stringify(l));
      const markType = typeof copy.mark === "string" ? copy.mark : copy.mark?.type;
      if (markType === "area") {
        if (typeof copy.mark === "string") copy.mark = { type: "area" };
        copy.mark.opacity = 1;
        if (mainDataKey) copy.data = { values: mainData };
      }
      layers.push(copy);
    });
  } else {
    const mainMark = typeof main.mark === "string" ? { type: main.mark } : { ...main.mark };
    mainMark.opacity = 1;
    layers.push({
      data: { values: mainData },
      mark: mainMark,
      encoding: main.encoding,
    });
  }

  // Add dev layer after main layers
  layers.push(devLayer);

  // Collect all datasets needed (main + dev)
  const allDatasets = { ...(main.datasets || {}) };

  // If dev spec is a layered chart (versioned), extract tag lines (rule + text layers)
  if (dev.layer && dev.layer.length > 1) {
    // Copy dev datasets so tag layers can reference them
    Object.assign(allDatasets, dev.datasets || {});
    dev.layer.forEach(l => {
      const markType = typeof l.mark === "string" ? l.mark : l.mark?.type;
      if (markType === "rule" || markType === "text") {
        layers.push(l);
      }
    });
  }

  return {
    $schema: main.$schema,
    config: main.config,
    datasets: allDatasets,
    title: main.title,
    width: main.width,
    height: main.height,
    layer: layers,
    resolve: { scale: { color: "independent" }, legend: { color: "independent" } },
  };
}

async function updateChart() {
  showLoading();

  try {
    let spec = await loadChart(state.currentRepo, state.currentVariant);

    // Merge develop BEFORE transforms so date filters apply to both layers
    if (showDevelopCheckbox.checked) {
      const devVariant = showTagsCheckbox.checked ? "develop-versioned" : "develop-clean";
      try {
        const devSpec = await loadChart(state.currentRepo, devVariant);
        spec = mergeWithDevelop(spec, devSpec);
      } catch {
        // Develop chart not available — silently ignore
      }
    }

    // Apply transforms (invert, date filter) AFTER merge
    spec = applyTransforms(spec);
    await renderChart(spec);
  } catch (error) {
    showError(state.currentRepo, state.currentVariant);
  }
}

// ========================================
// UI Update Functions
// ========================================

/**
 * Update dropdown selection
 */
function updateDropdown() {
  repoSelect.value = state.currentRepo;
}

/**
 * Update toggle selection
 */
function updateToggle() {
  showTagsCheckbox.checked = state.currentVariant === "versioned";
}

/**
 * Update all UI elements to reflect current state
 */
function updateUI() {
  updateDropdown();
  updateToggle();
}

// ========================================
// Event Handlers
// ========================================

/**
 * Handle repository dropdown change
 */
function onRepoChange(event) {
  state.currentRepo = event.target.value;
  updateToggle();
  updateURL();
  updateChart();
}

/**
 * Handle variant toggle change
 */
function onVariantChange(event) {
  state.currentVariant = event.target.checked ? "versioned" : "clean";
  updateURL();
  updateChart();
}

/**
 * Handle invert layers toggle
 */
function onInvertChange(event) {
  state.invertLayers = event.target.checked;
  updateChart();
}

/**
 * Handle browser back/forward navigation
 */
function onPopState() {
  const { repo, variant } = parseURL();
  state.currentRepo = repo;
  state.currentVariant = variant;
  updateUI();
  updateChart();
}

// ========================================
// Initialization
// ========================================

/**
 * Load repositories list from repos.json
 */
async function loadRepos() {
  try {
    const response = await fetch("charts/repos.json");
    if (!response.ok) {
      throw new Error(`Failed to load repos: ${response.status}`);
    }
    const data = await response.json();

    // Handle legacy array format: ["repo1", "repo2"]
    if (Array.isArray(data)) {
      const obj = {};
      await Promise.all(
        data.map(async (repo) => {
          const variants = ["clean"];
          const res = await fetch(`charts/${repo}-versioned.json`, { method: "HEAD" });
          if (res.ok) variants.push("versioned");
          obj[repo] = variants;
        })
      );
      return obj;
    }

    return data;
  } catch (error) {
    console.error("Error loading repos:", error);
    return {};
  }
}

/**
 * Populate dropdown with repositories
 */
function populateDropdown() {
  repoSelect.innerHTML = "";

  repoNames().forEach((repo) => {
    const option = document.createElement("option");
    option.value = repo;
    option.textContent = repo;
    repoSelect.appendChild(option);
  });
}

/**
 * Initialize the application
 */
async function init() {
  // Get DOM elements
  repoSelect = document.getElementById("repo-select");
  invertCheckbox = document.getElementById("invert-layers");
  chartContainer = document.getElementById("chart-container");
  granularitySelect = document.getElementById("granularity-select");
  regenerateBtn = document.getElementById("regenerate-btn");
  regenerateStatus = document.getElementById("regenerate-status");
  dateFrom = document.getElementById("date-from");
  dateTo = document.getElementById("date-to");
  showDevelopCheckbox = document.getElementById("show-develop");
  showTagsCheckbox = document.getElementById("show-tags");

  // Load repositories list
  state.repos = await loadRepos();

  // Populate dropdown
  populateDropdown();

  // Parse URL and set initial state
  const { repo, variant } = parseURL();
  state.currentRepo = repo;
  state.currentVariant = variant;

  // Update UI to reflect initial state
  updateUI();

  // Settings modal
  settingsModal = new bootstrap.Modal(document.getElementById("settings-modal"));
  document.getElementById("settings-btn").addEventListener("click", openSettings);
  document.getElementById("add-repo-btn").addEventListener("click", addRepoCard);
  document.getElementById("save-config-btn").addEventListener("click", saveConfig);
  document.getElementById("config-editor").addEventListener("click", onEditorClick);

  // Set up event listeners
  repoSelect.addEventListener("change", onRepoChange);
  showTagsCheckbox.addEventListener("change", onVariantChange);
  invertCheckbox.addEventListener("change", onInvertChange);
  regenerateBtn.addEventListener("click", onRegenerate);
  dateFrom.addEventListener("change", updateChart);
  dateTo.addEventListener("change", updateChart);
  showDevelopCheckbox.addEventListener("change", updateChart);
  document.getElementById("reset-dates-btn").addEventListener("click", () => {
    dateFrom.value = "";
    dateTo.value = "";
    updateChart();
  });
  window.addEventListener("popstate", onPopState);

  // Load and render initial chart
  await updateChart();
}

// ========================================
// Regeneration
// ========================================

async function onRegenerate() {
  const granularity = granularitySelect.value;
  const repo = state.currentRepo;
  regenerateBtn.disabled = true;
  regenerateStatus.textContent = `Generating ${repo}...`;

  try {
    const res = await fetch("/api/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ granularity, repo }),
    });
    const data = await res.json();
    if (data.error) {
      regenerateStatus.textContent = data.error;
      regenerateBtn.disabled = false;
      return;
    }
    pollStatus();
  } catch (e) {
    regenerateStatus.textContent = "Error: " + e.message;
    regenerateBtn.disabled = false;
  }
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (data.running) {
      regenerateStatus.textContent = data.repo
        ? `Generating ${data.repo}...`
        : "Starting...";
      setTimeout(pollStatus, 2000);
    } else if (data.error) {
      regenerateStatus.textContent = "Error: " + data.error;
      regenerateBtn.disabled = false;
    } else {
      regenerateStatus.textContent = "Done!";
      regenerateBtn.disabled = false;
      // Clear chart cache and force reload from server
      state.loadedCharts = {};
      await updateChart();
      setTimeout(() => { regenerateStatus.textContent = ""; }, 3000);
    }
  } catch (e) {
    regenerateStatus.textContent = "Error polling status";
    regenerateBtn.disabled = false;
  }
}

// ========================================
// Settings Modal
// ========================================

let settingsModal;

function createRepoCard(name, config, index) {
  return `
    <div class="card mb-3 repo-card" data-index="${index}">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <h6 class="card-title mb-0">
            <input type="text" class="form-control form-control-sm d-inline-block" style="width:auto"
              value="${name}" data-field="name" placeholder="repo-name">
          </h6>
          <button class="btn btn-outline-danger btn-sm remove-repo-btn" title="Remove">&times;</button>
        </div>
        <div class="mb-2">
          <label class="form-label small mb-1">Repository URL</label>
          <input type="text" class="form-control form-control-sm" value="${config.url}" data-field="url"
            placeholder="https://github.com/user/repo">
        </div>
        <div class="mb-2">
          <label class="form-label small mb-1">File extensions</label>
          <input type="text" class="form-control form-control-sm" value="${config.extensions}" data-field="extensions"
            placeholder=".ts,.js,.py,...">
        </div>
        <div>
          <label class="form-label small mb-1">Max samples</label>
          <input type="number" class="form-control form-control-sm" style="width:120px"
            value="${config.samples}" data-field="samples" min="1">
        </div>
      </div>
    </div>`;
}

async function openSettings() {
  const editor = document.getElementById("config-editor");
  const configStatus = document.getElementById("config-status");
  configStatus.textContent = "Loading...";

  try {
    const res = await fetch("/api/config");
    const config = await res.json();
    const entries = Object.entries(config);

    editor.innerHTML = entries
      .map(([name, cfg], i) => createRepoCard(name, cfg, i))
      .join("");

    configStatus.textContent = "";
  } catch (e) {
    configStatus.textContent = "Error loading config";
  }

  settingsModal.show();
}

function addRepoCard() {
  const editor = document.getElementById("config-editor");
  const index = editor.querySelectorAll(".repo-card").length;
  const defaultExt = ".dart,.swift,.h,.cpp,.cc,.c,.m,.mm,.kts,.kt,.java,.xml,.yaml,.yml,.json,.sql,.mjs,.js,.ts,.tsx,.jsx,.css,.scss,.html,.py,.sh,.bash,.zsh,.rb,.go,.rs,.cs,.csproj,.cshtml,.razor,.r,.lua,.php,.pl,.ex,.exs,.erl,.hs,.scala,.groovy,.gradle,.cmake,.makefile,.dockerfile,.tf,.hcl,.proto,.graphql,.gql,.toml,.ini,.cfg,.conf,.env,.properties,.plist,.entitlements,.pbxproj,.xcconfig,.xcworkspacedata,.storyboard,.xib,.nib,.md,.rst,.txt,.svg,.prisma,.http,.slnx,.sln,.lock";
  editor.insertAdjacentHTML("beforeend", createRepoCard("", { url: "", extensions: defaultExt, samples: 9999 }, index));
}

async function saveConfig() {
  const configStatus = document.getElementById("config-status");
  const cards = document.querySelectorAll(".repo-card");
  const config = {};

  for (const card of cards) {
    const name = card.querySelector('[data-field="name"]').value.trim();
    const url = card.querySelector('[data-field="url"]').value.trim();
    const extensions = card.querySelector('[data-field="extensions"]').value.trim();
    const samples = parseInt(card.querySelector('[data-field="samples"]').value) || 9999;

    if (!name || !url) continue;
    config[name] = { url, extensions, samples };
  }

  configStatus.textContent = "Saving...";

  try {
    const res = await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    const data = await res.json();
    if (data.saved) {
      configStatus.textContent = "Saved!";
      // Reload repos list and dropdown
      state.repos = await loadRepos();
      populateDropdown();
      const { repo, variant } = parseURL();
      state.currentRepo = repo;
      state.currentVariant = variant;
      updateUI();
      setTimeout(() => settingsModal.hide(), 1000);
    }
  } catch (e) {
    configStatus.textContent = "Error saving: " + e.message;
  }
}

function onEditorClick(e) {
  if (e.target.classList.contains("remove-repo-btn")) {
    e.target.closest(".repo-card").remove();
  }
}

// Start the application when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
