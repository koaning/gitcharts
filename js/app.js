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
let showVersionsCheckbox;
let versionToggle;
let invertCheckbox;
let chartContainer;
let granularitySelect;
let regenerateBtn;
let regenerateStatus;

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
function applyInvert(spec) {
  const copy = JSON.parse(JSON.stringify(spec));
  const encoding = copy.encoding || (copy.layer && copy.layer[0] && copy.layer[0].encoding);
  if (encoding && encoding.order) {
    encoding.order.sort = state.invertLayers ? "descending" : "ascending";
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
async function updateChart() {
  showLoading();

  try {
    const spec = await loadChart(state.currentRepo, state.currentVariant);
    await renderChart(applyInvert(spec));
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
  const variants = state.repos[state.currentRepo] || ["clean"];
  const hasVersioned = variants.includes("versioned");

  versionToggle.style.display = hasVersioned ? "" : "none";

  if (!hasVersioned && state.currentVariant === "versioned") {
    state.currentVariant = "clean";
    showVersionsCheckbox.checked = false;
    updateURL();
  }

  showVersionsCheckbox.checked = state.currentVariant === "versioned";
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
  showVersionsCheckbox = document.getElementById("show-versions");
  versionToggle = document.getElementById("version-toggle");
  invertCheckbox = document.getElementById("invert-layers");
  chartContainer = document.getElementById("chart-container");
  granularitySelect = document.getElementById("granularity-select");
  regenerateBtn = document.getElementById("regenerate-btn");
  regenerateStatus = document.getElementById("regenerate-status");

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
  showVersionsCheckbox.addEventListener("change", onVariantChange);
  invertCheckbox.addEventListener("change", onInvertChange);
  regenerateBtn.addEventListener("click", onRegenerate);
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
