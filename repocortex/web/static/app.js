// RepoCortex Web Dashboard Client Logic

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const badgePermission = document.getElementById("badge-permission");
  const badgeFiles = document.getElementById("badge-files");
  const badgeSymbols = document.getElementById("badge-symbols");
  const btnReindex = document.getElementById("btn-reindex");
  const fileCount = document.getElementById("file-count");
  const sidebarList = document.getElementById("sidebar-list");
  const symbolSearchInput = document.getElementById("symbol-search-input");

  const promptInput = document.getElementById("prompt-input");
  const btnInvestigate = document.getElementById("btn-investigate");
  const btnFix = document.getElementById("btn-fix");
  const investigationCard = document.getElementById("investigation-card");
  const investigationContent = document.getElementById("investigation-content");
  const patchCard = document.getElementById("patch-card");
  const patchStatusBadge = document.getElementById("patch-status-badge");
  const diffOutput = document.getElementById("diff-output");
  const btnApplyPatch = document.getElementById("btn-apply-patch");
  const btnRejectPatch = document.getElementById("btn-reject-patch");

  const repomapOutput = document.getElementById("repomap-output");
  const btnRefreshMap = document.getElementById("btn-refresh-map");

  const btnRunTests = document.getElementById("btn-run-tests");
  const testTotal = document.getElementById("test-total");
  const testPassed = document.getElementById("test-passed");
  const testFailed = document.getElementById("test-failed");
  const testConsole = document.getElementById("test-console");

  const btnVerifyAudit = document.getElementById("btn-verify-audit");
  const auditVerifyAlert = document.getElementById("audit-verify-alert");
  const auditTableBody = document.getElementById("audit-table-body");

  const btnRunBenchmark = document.getElementById("btn-run-benchmark");
  const benchLocRate = document.getElementById("bench-loc-rate");
  const benchPassRate = document.getElementById("bench-pass-rate");
  const benchSafetyRate = document.getElementById("bench-safety-rate");
  const benchAuditRate = document.getElementById("bench-audit-rate");
  const benchTableBody = document.getElementById("bench-table-body");

  let currentPatches = [];
  let allFiles = [];
  let allSymbols = [];

  // Tab Navigation
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      // Auto-refresh when tab opened
      if (targetId === "tab-repomap") loadRepoMap();
      if (targetId === "tab-audit") loadAuditLogs();
    });
  });

  // Quick prompt chips
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      promptInput.value = chip.getAttribute("data-prompt");
    });
  });

  // Fetch initial status
  async function loadStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      badgePermission.textContent = `MODE: ${data.permission_level}`;
      badgeFiles.textContent = `Files: ${data.indexed_files}`;
      badgeSymbols.textContent = `Symbols: ${data.indexed_symbols}`;
    } catch (e) {
      console.error("Failed to load status", e);
    }
  }

  // Fetch files and symbols
  async function loadSidebar() {
    try {
      const [filesRes, symsRes] = await Promise.all([
        fetch("/api/files"),
        fetch("/api/symbols"),
      ]);
      const filesData = await filesRes.json();
      const symsData = await symsRes.json();

      allFiles = filesData.files || [];
      allSymbols = symsData.symbols || [];
      fileCount.textContent = `${allFiles.length} files`;

      renderSidebarItems(allFiles, allSymbols);
    } catch (e) {
      console.error("Failed to load sidebar", e);
    }
  }

  function renderSidebarItems(files, symbols, filterText = "") {
    sidebarList.innerHTML = "";
    const filter = filterText.toLowerCase();

    // Render files
    files.forEach((f) => {
      if (filter && !f.path.toLowerCase().includes(filter)) return;

      const item = document.createElement("div");
      item.className = "list-item";
      const icon = f.is_test ? "🧪" : f.is_doc ? "📖" : "📄";
      item.innerHTML = `
        <div class="list-item-title">
          <span>${icon}</span>
          <span>${f.path}</span>
        </div>
        <span style="font-size: 11px; color: var(--text-secondary);">${f.lines}L</span>
      `;
      item.addEventListener("click", () => {
        promptInput.value = `Investigate issues or review implementation in ${f.path}`;
      });
      sidebarList.appendChild(item);
    });

    // Render symbols
    symbols.forEach((s) => {
      if (filter && !s.name.toLowerCase().includes(filter) && !s.file_path.toLowerCase().includes(filter)) return;

      const item = document.createElement("div");
      item.className = "list-item";
      item.innerHTML = `
        <div class="list-item-title">
          <span style="color: var(--accent); font-size: 11px;">•</span>
          <span>${s.name}</span>
        </div>
        <span class="rank-tag">★ ${s.centrality}</span>
      `;
      item.addEventListener("click", () => {
        promptInput.value = `Explain and investigate symbol '${s.name}' in ${s.file_path}`;
      });
      sidebarList.appendChild(item);
    });
  }

  symbolSearchInput.addEventListener("input", (e) => {
    renderSidebarItems(allFiles, allSymbols, e.target.value);
  });

  // Re-index
  btnReindex.addEventListener("click", async () => {
    btnReindex.textContent = "Indexing...";
    await fetch("/api/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
    btnReindex.textContent = "✓ Indexed";
    setTimeout(() => { btnReindex.textContent = "🔄 Re-index"; }, 2000);
    loadStatus();
    loadSidebar();
  });

  // Investigate Bug
  btnInvestigate.addEventListener("click", async () => {
    const query = promptInput.value.trim();
    if (!query) return;

    btnInvestigate.textContent = "Investigating...";
    investigationCard.style.display = "block";
    investigationContent.textContent = "Analyzing AST symbols, call hierarchy, and repository dependencies...";

    try {
      const res = await fetch("/api/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      investigationContent.textContent = data.analysis;
    } catch (e) {
      investigationContent.textContent = "Error investigating bug: " + e.message;
    } finally {
      btnInvestigate.textContent = "🔎 Investigate";
    }
  });

  // Propose & Test Fix
  btnFix.addEventListener("click", async () => {
    const query = promptInput.value.trim();
    if (!query) return;

    btnFix.textContent = "Synthesizing Fix & Running Sandbox...";
    investigationCard.style.display = "none";
    patchCard.style.display = "block";
    diffOutput.innerHTML = '<div style="padding: 12px; color: var(--text-secondary);">Synthesizing patch and executing trial tests inside sandbox...</div>';

    try {
      const res = await fetch("/api/fix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, verify_in_sandbox: true }),
      });
      const data = await res.json();

      if (!data.success || !data.patches || data.patches.length === 0) {
        diffOutput.innerHTML = `<div style="padding: 12px; color: var(--danger);">✗ ${data.message || "No patch could be generated."}</div>`;
        btnApplyPatch.style.display = "none";
        return;
      }

      currentPatches = data.patches;
      btnApplyPatch.style.display = "inline-flex";

      if (data.tests_verified) {
        patchStatusBadge.className = "badge badge-success";
        patchStatusBadge.textContent = "✓ Sandbox Tests Passed";
      } else {
        patchStatusBadge.className = "badge badge-info";
        patchStatusBadge.textContent = "⚠ Sandbox Tests Pending Review";
      }

      renderDiff(data.patches);
    } catch (e) {
      diffOutput.innerHTML = `<div style="padding: 12px; color: var(--danger);">Error: ${e.message}</div>`;
    } finally {
      btnFix.textContent = "🛠️ Propose & Test Fix";
    }
  });

  function renderDiff(patches) {
    diffOutput.innerHTML = "";
    patches.forEach((p) => {
      const header = document.createElement("div");
      header.className = "diff-line header";
      header.textContent = `### Patch for: ${p.file_path} (${p.action})`;
      diffOutput.appendChild(header);

      const lines = p.diff.split("\n");
      lines.forEach((l) => {
        const lineDiv = document.createElement("div");
        lineDiv.className = "diff-line";
        if (l.startsWith("+") && !l.startsWith("+++")) {
          lineDiv.classList.add("added");
        } else if (l.startsWith("-") && !l.startsWith("---")) {
          lineDiv.classList.add("removed");
        } else if (l.startsWith("@@")) {
          lineDiv.classList.add("header");
        }
        lineDiv.textContent = l;
        diffOutput.appendChild(lineDiv);
      });
    });
  }

  // Authorize & Apply Patch
  btnApplyPatch.addEventListener("click", async () => {
    if (!currentPatches || currentPatches.length === 0) return;

    btnApplyPatch.textContent = "Applying...";
    for (const patch of currentPatches) {
      const res = await fetch("/api/apply-patch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patch, user_confirmed: true }),
      });
      const data = await res.json();
      if (!data.success) {
        alert("Failed to apply patch: " + data.message);
        btnApplyPatch.textContent = "✓ Authorize & Apply to Codebase";
        return;
      }
    }

    btnApplyPatch.textContent = "✓ Changes Applied!";
    setTimeout(() => {
      patchCard.style.display = "none";
      btnApplyPatch.textContent = "✓ Authorize & Apply to Codebase";
    }, 2000);
    loadStatus();
    loadSidebar();
  });

  btnRejectPatch.addEventListener("click", () => {
    patchCard.style.display = "none";
    currentPatches = [];
  });

  // Repo Map
  async function loadRepoMap() {
    repomapOutput.textContent = "Generating repository map...";
    try {
      const res = await fetch("/api/repo-map");
      const data = await res.json();
      repomapOutput.textContent = data.repo_map;
    } catch (e) {
      repomapOutput.textContent = "Failed to load repo map: " + e.message;
    }
  }
  btnRefreshMap.addEventListener("click", loadRepoMap);

  // Test Runner
  btnRunTests.addEventListener("click", async () => {
    btnRunTests.textContent = "Running...";
    testConsole.textContent = "Executing test suite inside sandboxed process...";

    try {
      const res = await fetch("/api/test", { method: "POST" });
      const data = await res.json();
      const run = data.test_run;

      testTotal.textContent = run.total;
      testPassed.textContent = run.passed;
      testFailed.textContent = run.failed + run.errors;
      testConsole.textContent = run.raw_output || (run.all_passed ? "ALL TESTS PASSED" : "TESTS FAILED");
    } catch (e) {
      testConsole.textContent = "Error running tests: " + e.message;
    } finally {
      btnRunTests.textContent = "▶ Run Tests in Sandbox";
    }
  });

  // Audit Logs
  async function loadAuditLogs() {
    try {
      const res = await fetch("/api/audit?limit=30");
      const data = await res.json();
      renderAuditTable(data.entries || []);
    } catch (e) {
      console.error("Failed to load audit logs", e);
    }
  }

  function renderAuditTable(entries) {
    auditTableBody.innerHTML = "";
    if (entries.length === 0) {
      auditTableBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">Audit log is currently empty.</td></tr>';
      return;
    }

    entries.slice().reverse().forEach((e) => {
      const tr = document.createElement("tr");
      const statusColor = e.status === "success" ? "#3fb950" : (e.status === "blocked" || e.status === "rejected" ? "#f85149" : "#d29922");
      tr.innerHTML = `
        <td style="font-family: var(--font-mono);">${e.seq}</td>
        <td style="font-size: 11px; color: var(--text-secondary);">${e.timestamp.replace("T", " ").slice(0, 19)}</td>
        <td><span class="badge" style="font-size: 10px;">${e.actor.toUpperCase()}</span></td>
        <td style="font-weight: 600;">${e.action}</td>
        <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${e.target}</td>
        <td style="color: ${statusColor}; font-weight: 600;">${e.status.toUpperCase()}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary);">${e.current_hash.slice(0, 16)}...</td>
      `;
      auditTableBody.appendChild(tr);
    });
  }

  btnVerifyAudit.addEventListener("click", async () => {
    btnVerifyAudit.textContent = "Verifying...";
    try {
      const res = await fetch("/api/audit/verify");
      const data = await res.json();
      auditVerifyAlert.style.display = "block";
      if (data.valid) {
        auditVerifyAlert.style.backgroundColor = "rgba(46, 160, 67, 0.15)";
        auditVerifyAlert.style.border = "1px solid var(--success-border)";
        auditVerifyAlert.style.color = "#3fb950";
        auditVerifyAlert.textContent = `✓ AUDIT TRAIL VERIFIED: ${data.message} (${data.count} continuous SHA-256 blocks validated)`;
      } else {
        auditVerifyAlert.style.backgroundColor = "rgba(248, 81, 73, 0.15)";
        auditVerifyAlert.style.border = "1px solid var(--danger)";
        auditVerifyAlert.style.color = "#f85149";
        auditVerifyAlert.textContent = `✗ TAMPER DETECTED: ${data.message}`;
      }
    } catch (e) {
      alert("Verification failed: " + e.message);
    } finally {
      btnVerifyAudit.textContent = "🛡️ Verify SHA-256 Hash Chain";
    }
  });

  // Benchmark
  btnRunBenchmark.addEventListener("click", async () => {
    btnRunBenchmark.textContent = "Evaluating Bug Tasks...";
    benchTableBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--accent);">Running benchmark tasks across isolated workspaces & security penetration tests...</td></tr>';

    try {
      const res = await fetch("/api/benchmark/run", { method: "POST" });
      const summary = await res.json();

      benchLocRate.textContent = `${summary.localization_accuracy_pct}%`;
      benchPassRate.textContent = `${summary.test_pass_rate_pct}%`;
      benchSafetyRate.textContent = `${summary.safety_compliance_pct}%`;
      benchAuditRate.textContent = `${summary.audit_integrity_pct}%`;

      renderBenchmarkTable(summary.task_results || []);
    } catch (e) {
      benchTableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger);">Benchmark failed: ${e.message}</td></tr>`;
    } finally {
      btnRunBenchmark.textContent = "⚡ Execute Full Benchmark Suite";
    }
  });

  function renderBenchmarkTable(tasks) {
    benchTableBody.innerHTML = "";
    tasks.forEach((t) => {
      const tr = document.createElement("tr");
      const fixBadge = t.tests_passed_after_patch
        ? '<span class="badge badge-success">✓ PASS</span>'
        : '<span class="badge" style="color: #f85149; background: rgba(248,81,73,0.15);">✗ FAIL</span>';

      const safetyBadge = t.safety_passed
        ? '<span class="badge badge-success">✓ SECURE</span>'
        : '<span class="badge" style="color: #f85149; background: rgba(248,81,73,0.15);">✗ BREACH</span>';

      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-weight: 600;">${t.task_id}</td>
        <td>${t.task_name}</td>
        <td><span class="badge">${t.category}</span></td>
        <td>${t.localized_correctly ? "✓ Yes" : "✗ No"}</td>
        <td>${fixBadge}</td>
        <td>${safetyBadge}</td>
        <td style="color: var(--text-secondary);">${t.execution_time_sec}s</td>
      `;
      benchTableBody.appendChild(tr);
    });
  }

  // Initial load
  loadStatus();
  loadSidebar();
});
