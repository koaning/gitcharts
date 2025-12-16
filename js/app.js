import { REPOS } from './config.js';

// Application State
const state = {
    currentRepo: 'human-learn',
    currentVariant: 'clean',
    loadedCharts: {} // Cache: {repo-variant: vegaSpec}
};

// DOM Elements
let repoSelect;
let cleanRadio;
let versionedRadio;
let chartContainer;

// ========================================
// URL State Management
// ========================================

/**
 * Parse URL hash to extract repo and variant
 * Format: #repo-name/variant
 * Example: #human-learn/versioned
 */
function parseURL() {
    const hash = window.location.hash.slice(1); // Remove the '#'

    if (!hash) {
        return {
            repo: 'human-learn',
            variant: 'clean'
        };
    }

    const parts = hash.split('/');
    const repo = parts[0] || 'human-learn';
    const variant = parts[1] || 'clean';

    // Validate repo exists in config
    const validRepo = REPOS.find(r => r.name === repo) ? repo : 'human-learn';

    // Validate variant is clean or versioned
    const validVariant = ['clean', 'versioned'].includes(variant) ? variant : 'clean';

    return {
        repo: validRepo,
        variant: validVariant
    };
}

/**
 * Update URL hash based on current state
 */
function updateURL() {
    const hash = `#${state.currentRepo}/${state.currentVariant}`;
    if (window.location.hash !== hash) {
        window.history.pushState(null, '', hash);
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
        const response = await fetch(`charts/${repo}-${variant}.json`);

        if (!response.ok) {
            throw new Error(`Chart not found: ${response.status}`);
        }

        const spec = await response.json();

        // Cache the loaded chart
        state.loadedCharts[cacheKey] = spec;

        return spec;
    } catch (error) {
        console.error('Error loading chart:', error);
        throw error;
    }
}

/**
 * Render chart using Vega-Embed
 */
async function renderChart(spec) {
    const embedOpt = {
        mode: 'vega-lite',
        actions: {
            export: true,      // Enable PNG download
            source: false,     // Disable view source
            compiled: false,   // Disable view compiled Vega
            editor: false      // Disable open in editor
        }
    };

    try {
        // Clear container
        chartContainer.innerHTML = '';
        chartContainer.className = '';

        // Embed chart
        await vegaEmbed('#chart-container', spec, embedOpt);
    } catch (error) {
        console.error('Error rendering chart:', error);
        throw error;
    }
}

/**
 * Show loading state
 */
function showLoading() {
    chartContainer.className = 'loading';
    chartContainer.innerHTML = '<p>Loading chart...</p>';
}

/**
 * Show error message
 */
function showError(repo, variant) {
    chartContainer.className = 'error';

    // Get the repo URL from repos.txt for the error message
    const repoUrls = {
        'human-learn': 'https://github.com/koaning/human-learn',
        'scikit-lego': 'https://github.com/koaning/scikit-lego'
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
    if (state.currentVariant === 'clean') {
        cleanRadio.checked = true;
    } else {
        versionedRadio.checked = true;
    }
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
    updateURL();
    updateChart();
}

/**
 * Handle variant toggle change
 */
function onVariantChange(event) {
    state.currentVariant = event.target.value;
    updateURL();
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
 * Populate dropdown with repositories
 */
function populateDropdown() {
    repoSelect.innerHTML = '';

    REPOS.forEach(repo => {
        const option = document.createElement('option');
        option.value = repo.name;
        option.textContent = repo.displayName;
        repoSelect.appendChild(option);
    });
}

/**
 * Initialize the application
 */
async function init() {
    // Get DOM elements
    repoSelect = document.getElementById('repo-select');
    cleanRadio = document.getElementById('clean');
    versionedRadio = document.getElementById('versioned');
    chartContainer = document.getElementById('chart-container');

    // Populate dropdown
    populateDropdown();

    // Parse URL and set initial state
    const { repo, variant } = parseURL();
    state.currentRepo = repo;
    state.currentVariant = variant;

    // Update UI to reflect initial state
    updateUI();

    // Set up event listeners
    repoSelect.addEventListener('change', onRepoChange);
    cleanRadio.addEventListener('change', onVariantChange);
    versionedRadio.addEventListener('change', onVariantChange);
    window.addEventListener('popstate', onPopState);

    // Load and render initial chart
    await updateChart();
}

// Start the application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
