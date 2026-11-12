/**
 * frontend/js/unified-analysis.js
 * 
 * Unified Analysis Controller - ORC-powered Commit Analysis
 * 
 * Integrates:
 * - Metadata Pipeline prediction (failure probability)
 * - Graph synchronization status
 * - Suspicious file identification (graph centrality)
 * - SHAP-based feature importance (drivers)
 */

import { api } from "./api.js";
import { toast } from "./utils.js";

export class UnifiedAnalysisController {
  constructor() {
    this.currentAnalysis = null;
  }

  init() {
    this.bindEvents();
  }

  bindEvents() {
    // Form submission
    document.getElementById("unified-btn-analyze").addEventListener("click", () => {
      this.performAnalysis();
    });

    // Allow Enter key in input fields
    ["unified-repo-input", "unified-sha-input", "unified-path-input"].forEach(id => {
      document.getElementById(id).addEventListener("keypress", (e) => {
        if (e.key === "Enter") this.performAnalysis();
      });
    });
  }

  async performAnalysis() {
    const repoId = document.getElementById("unified-repo-input").value.trim();
    const targetSha = document.getElementById("unified-sha-input").value.trim();
    const repoPath = document.getElementById("unified-path-input").value.trim();

    // Validation
    if (!repoId) {
      toast("Please enter repository (owner/repo)", "error");
      return;
    }
    if (!targetSha) {
      toast("Please enter commit SHA", "error");
      return;
    }
    if (!repoPath) {
      toast("Please enter repository path", "error");
      return;
    }

    // Show loading
    const btn = document.getElementById("unified-btn-analyze");
    const indicator = document.getElementById("unified-loading-indicator");
    btn.disabled = true;
    indicator.style.display = "inline-block";

    try {
      this.currentAnalysis = await api.analyzeCommitViaOrc(
        repoId,
        targetSha,
        repoPath
      );

      this.renderAnalysisResults();
      toast("Analysis complete", "success");

    } catch (err) {
      console.error("Analysis failed:", err);
      toast(`Analysis failed: ${err.message}`, "error");
      document.getElementById("unified-results-container").style.display = "none";
      document.getElementById("unified-empty-state").style.display = "block";

    } finally {
      btn.disabled = false;
      indicator.style.display = "none";
    }
  }

  renderAnalysisResults() {
    const resultsContainer = document.getElementById("unified-results-container");
    const emptyState = document.getElementById("unified-empty-state");

    resultsContainer.style.display = "block";
    emptyState.style.display = "none";

    const analysis = this.currentAnalysis;

    // Render prediction summary
    this.renderPredictionSummary(analysis);

    // Render SHAP drivers
    this.renderSHAPDrivers(analysis);

    // Render suspicious files
    this.renderSuspiciousFiles(analysis);
  }

  renderPredictionSummary(analysis) {
    const probability = analysis.failure_probability;
    const verdict = analysis.verdict;
    const processingTime = analysis.processing_time_ms;
    const graphStatus = analysis.graph_status;

    // Determine color based on probability
    let verdictColor = "var(--status-unknown)";
    let verdictText = verdict;

    if (probability < 0.30) {
      verdictColor = "var(--status-healthy)";
      verdictText = "FAST-TRACK";
    } else if (probability < 0.60) {
      verdictColor = "var(--status-warning)";
      verdictText = "STANDARD GATE";
    } else if (probability < 0.80) {
      verdictColor = "var(--status-danger)";
      verdictText = "ALERT";
    } else {
      verdictColor = "var(--status-critical)";
      verdictText = "PRE-MERGE BLOCK";
    }

    // Update verdict badge
    const badge = document.getElementById("unified-verdict-badge");
    badge.textContent = verdictText;
    badge.style.background = verdictColor;

    // Update probability display
    const probabilityVal = document.getElementById("unified-probability-val");
    probabilityVal.textContent = `${(probability * 100).toFixed(1)}%`;
    probabilityVal.style.color = verdictColor;

    // Update progress bar
    const progressBar = document.getElementById("unified-probability-bar");
    progressBar.style.width = `${probability * 100}%`;
    progressBar.style.background = verdictColor;

    // Update rationale
    const rationale = document.getElementById("unified-probability-rationale");
    const reasons = {
      "FAST-TRACK": "Low risk - fast-track recommended",
      "STANDARD GATE": "Moderate risk - standard QA gates",
      "ALERT": "High risk - requires review",
      "PRE-MERGE BLOCK": "Critical risk - block merge"
    };
    rationale.textContent = reasons[verdictText] || verdict;

    // Update metadata
    document.getElementById("unified-time-val").textContent = `${processingTime.toFixed(0)}ms`;
    document.getElementById("unified-graph-status").textContent = graphStatus;
  }

  renderSHAPDrivers(analysis) {
    const drivers = analysis.shap_drivers || { positive: [], negative: [] };

    const positiveList = document.getElementById("unified-shap-positive-list");
    positiveList.innerHTML = "";

    if (drivers.positive && drivers.positive.length > 0) {
      drivers.positive.forEach(([featureName, value]) => {
        const item = document.createElement("div");
        item.className = "text-xs";
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.padding = "0.35rem 0.5rem";
        item.style.background = "rgba(239, 68, 68, 0.1)";
        item.style.borderRadius = "0.25rem";
        item.innerHTML = `
          <span>${featureName}</span>
          <span class="font-mono font-bold" style="color: var(--status-danger);">${value.toFixed(4)}</span>
        `;
        positiveList.appendChild(item);
      });
    } else {
      positiveList.innerHTML = '<div class="text-xs text-muted">--</div>';
    }

    const negativeList = document.getElementById("unified-shap-negative-list");
    negativeList.innerHTML = "";

    if (drivers.negative && drivers.negative.length > 0) {
      drivers.negative.forEach(([featureName, value]) => {
        const item = document.createElement("div");
        item.className = "text-xs";
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.padding = "0.35rem 0.5rem";
        item.style.background = "rgba(34, 197, 94, 0.1)";
        item.style.borderRadius = "0.25rem";
        item.innerHTML = `
          <span>${featureName}</span>
          <span class="font-mono font-bold" style="color: var(--status-healthy);">${value.toFixed(4)}</span>
        `;
        negativeList.appendChild(item);
      });
    } else {
      negativeList.innerHTML = '<div class="text-xs text-muted">--</div>';
    }
  }

  renderSuspiciousFiles(analysis) {
    const suspiciousFiles = analysis.suspicious_files || [];
    const container = document.getElementById("unified-suspicious-files-list");
    const countDisplay = document.getElementById("unified-suspicious-count");

    countDisplay.textContent = `${suspiciousFiles.length} file${suspiciousFiles.length !== 1 ? "s" : ""}`;

    if (suspiciousFiles.length === 0) {
      container.innerHTML = '<div class="text-xs text-muted" style="padding: 1rem;">No suspicious files identified</div>';
      return;
    }

    container.innerHTML = "";

    suspiciousFiles.forEach((file, index) => {
      const item = document.createElement("div");
      item.style.padding = "0.75rem";
      item.style.borderBottom = "1px solid var(--border-color)";
      item.style.display = "flex";
      item.style.justifyContent = "space-between";
      item.style.alignItems = "flex-start";

      const centrality = file.centrality_score;
      const centrality_percent = (centrality * 100).toFixed(1);

      let riskColor = "var(--status-healthy)";
      if (centrality > 0.7) riskColor = "var(--status-critical)";
      else if (centrality > 0.5) riskColor = "var(--status-danger)";
      else if (centrality > 0.3) riskColor = "var(--status-warning)";

      const reasonsHtml = file.reasons && file.reasons.length > 0
        ? file.reasons.map(r => `<li class="text-xs text-muted">${r}</li>`).join("")
        : '<li class="text-xs text-muted">No specific reasons identified</li>';

      item.innerHTML = `
        <div style="flex: 1;">
          <div class="font-mono text-sm font-bold" style="margin-bottom: 0.35rem;">${file.file_path}</div>
          <div style="display: flex; gap: 1rem; margin-bottom: 0.5rem;">
            <div>
              <span class="text-xs text-muted">Centrality:</span>
              <div class="progress-track-small" style="width: 100px; height: 4px; background: rgba(0,0,0,0.2); border-radius: 2px; margin-top: 2px;">
                <div style="width: ${centrality_percent}%; height: 100%; background: ${riskColor}; border-radius: 2px;"></div>
              </div>
            </div>
            <span class="font-mono font-bold" style="color: ${riskColor};">${centrality_percent}%</span>
          </div>
          <ul style="margin: 0; padding-left: 1rem;">
            ${reasonsHtml}
          </ul>
        </div>
      `;
      container.appendChild(item);
    });
  }
}

export const unifiedAnalysisController = new UnifiedAnalysisController();
