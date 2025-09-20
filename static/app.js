const form = document.getElementById("searchForm");
const usernameInput = document.getElementById("usernameInput");
const statusArea = document.getElementById("statusArea");
const resultsGrid = document.getElementById("resultsGrid");
const historyList = document.getElementById("historyList");
const clearBtn = document.getElementById("clearBtn");

// Bulk search elements
const bulkInput = document.getElementById("bulkInput");
const bulkType = document.getElementById("bulkType");
const bulkSearchBtn = document.getElementById("bulkSearchBtn");
const exportSection = document.getElementById("exportSection");
const exportJson = document.getElementById("exportJson");
const exportCsv = document.getElementById("exportCsv");
const exportStatus = document.getElementById("exportStatus");

// Watchlist and filtering elements
const watchlistInput = document.getElementById("watchlistInput");
const addToWatchlist = document.getElementById("addToWatchlist");
const watchlistItems = document.getElementById("watchlistItems");
const monitorWatchlist = document.getElementById("monitorWatchlist");
const filterBtns = document.querySelectorAll(".filter-btn");
const sortHistory = document.getElementById("sortHistory");
const totalSearches = document.getElementById("totalSearches");
const foundResults = document.getElementById("foundResults");

// Global variables
let currentBulkResults = null;
let allHistory = [];
let currentFilter = "all";
let currentSort = "recent";

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

async function fetchHistory() {
  historyList.innerHTML = "<div class='text-muted'>Loading...</div>";
  try {
    const res = await fetch("/api/history");
    const j = await res.json();
    allHistory = j.history || [];
    
    // Update stats
    updateStats();
    
    // Apply current filter and sort
    displayFilteredHistory();
    
  } catch (e) {
    historyList.innerHTML = "<div class='text-danger'>Failed to load history</div>";
  }
}

function updateStats() {
  totalSearches.textContent = allHistory.length;
  
  // Count found results (simplified estimation)
  let foundCount = 0;
  allHistory.forEach(item => {
    const result = item.result;
    if (result && typeof result === 'object') {
      if (result.type === 'username' && result.username_results) {
        const platforms = Object.values(result.username_results);
        foundCount += platforms.filter(p => p.exists).length;
      } else if (result.ok || result.type) {
        foundCount++;
      }
    }
  });
  foundResults.textContent = foundCount;
}

function getItemType(item) {
  const result = item.result;
  if (result && result.type) {
    return result.type;
  }
  // Fallback detection
  const username = item.username;
  if (username.includes('@')) return 'email';
  if (username.match(/^\+?\d+/)) return 'phone';
  if (username.match(/^\d+\.\d+\.\d+\.\d+$/)) return 'ip'; // IPv4
  if (username.match(/^[0-9a-fA-F:]+$/) && username.includes(':')) return 'ip'; // IPv6
  if (username.includes(' ') && username.split(' ').length >= 2) return 'name';
  return 'username';
}

function displayFilteredHistory() {
  historyList.innerHTML = "";
  
  if (allHistory.length === 0) {
    historyList.innerHTML = "<div class='text-muted'>No recent searches.</div>";
    return;
  }
  
  // Filter history
  let filteredHistory = allHistory;
  if (currentFilter !== "all") {
    filteredHistory = allHistory.filter(item => getItemType(item) === currentFilter);
  }
  
  // Sort history
  filteredHistory.sort((a, b) => {
    switch (currentSort) {
      case "oldest":
        return new Date(a.checked_at) - new Date(b.checked_at);
      case "alphabetical":
        return a.username.localeCompare(b.username);
      case "type":
        return getItemType(a).localeCompare(getItemType(b));
      default: // recent
        return new Date(b.checked_at) - new Date(a.checked_at);
    }
  });
  
  // Display history
  filteredHistory.forEach(item => {
    const row = el("div", "history-item mb-2 p-2 border rounded");
    const t = new Date(item.checked_at).toLocaleString();
    const itemType = getItemType(item);
    const typeIcon = {
      email: "fa-envelope",
      phone: "fa-phone",
      name: "fa-user",
      username: "fa-at",
      ip: "fa-globe"
    }[itemType] || "fa-search";
    
    row.innerHTML = `
      <div class="d-flex justify-content-between align-items-start">
        <div style="flex: 1;">
          <div class="d-flex align-items-center gap-1">
            <i class="fa-solid ${typeIcon}" style="color: #6c757d;"></i>
            <strong>${item.username}</strong>
            <span class="badge bg-light text-dark">${itemType}</span>
          </div>
          <div class="text-muted small">${t}</div>
        </div>
        <div class="d-flex gap-1">
          <button class="btn btn-sm btn-outline-primary" onclick="renderResults('${item.username}', ${JSON.stringify(item.result).replace(/"/g, '&quot;')})">
            <i class="fa-solid fa-eye"></i>
          </button>
          <button class="btn btn-sm btn-outline-success" onclick="addItemToWatchlist('${item.username}')">
            <i class="fa-solid fa-plus"></i>
          </button>
        </div>
      </div>
    `;
    row.style.cursor = "pointer";
    row.onclick = (e) => {
      if (!e.target.closest('button')) {
        renderResults(item.username, item.result);
      }
    };
    historyList.appendChild(row);
  });
  
  if (filteredHistory.length === 0) {
    historyList.innerHTML = `<div class='text-muted'>No ${currentFilter} searches found.</div>`;
  }
}

function clearResults() {
  resultsGrid.innerHTML = "";
  statusArea.innerHTML = "";
}

function showLoadingSpinner(message = "Loading...") {
  return `
    <div class="d-flex justify-content-center align-items-center py-5">
      <div class="text-center">
        <div class="spinner-border text-primary mb-3" style="width: 3rem; height: 3rem;" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        <div class="h6 text-muted">${message}</div>
        <div class="text-muted small">Please wait while we process your request...</div>
      </div>
    </div>
  `;
}

function showSuccessAlert(message, type = "success") {
  const alertClass = type === "success" ? "alert-success" : type === "warning" ? "alert-warning" : "alert-danger";
  const icon = type === "success" ? "fas fa-check-circle" : type === "warning" ? "fas fa-exclamation-triangle" : "fas fa-times-circle";
  
  return `
    <div class="alert ${alertClass} alert-dismissible fade show shadow-sm" role="alert" style="border-radius: 0.75rem; border: none;">
      <i class="${icon} me-2"></i>
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>
  `;
}

function createModernCard(title, subtitle, status, content, options = {}) {
  const cardClass = options.highlighted ? "custom-card border-primary" : "custom-card";
  const statusColor = status === "success" ? "text-success" : status === "error" ? "text-danger" : "text-warning";
  const statusIcon = status === "success" ? "fas fa-check-circle" : status === "error" ? "fas fa-times-circle" : "fas fa-exclamation-triangle";
  
  return `
    <div class="${cardClass} mb-3 h-100" style="transition: all 0.3s ease; border-radius: 1rem; overflow: hidden;">
      <div class="card-body p-4">
        <div class="d-flex justify-content-between align-items-start mb-3">
          <div class="flex-grow-1">
            <h6 class="card-title mb-1 text-primary" style="font-weight: 600;">
              ${options.icon ? `<i class="${options.icon} me-2"></i>` : ''}
              ${title}
            </h6>
            ${subtitle ? `<p class="text-muted small mb-0">${subtitle}</p>` : ''}
          </div>
          <div class="text-end">
            <span class="${statusColor}">
              <i class="${statusIcon} me-1"></i>
              ${status.charAt(0).toUpperCase() + status.slice(1)}
            </span>
          </div>
        </div>
        <div class="card-content">
          ${content}
        </div>
        ${options.actions ? `
          <div class="card-actions mt-3 pt-3 border-top">
            ${options.actions}
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function renderResults(username, resultObj) {
  clearResults();
  const title = el("div", "mb-2");
  title.innerHTML = `<h5>Results for <code>${username}</code></h5>`;
  statusArea.appendChild(title);

  // Check result type
  if (resultObj.type === "email") {
    renderEmailResults(resultObj);
    return;
  } else if (resultObj.type === "phone") {
    renderPhoneResults(resultObj);
    return;
  } else if (resultObj.type === "ip") {
    renderIPResults(resultObj);
    return;
  } else if (resultObj.type === "name") {
    renderNameResults(resultObj);
    return;
  } else if (resultObj.type === "enhanced_username") {
    renderEnhancedUsernameResults(resultObj);
    return;
  } else if (resultObj.type === "username") {
    // Handle username results with type wrapper
    renderUsernameResults(resultObj.username_results, username);
    return;
  }

  // Handle direct username results (legacy format)
  renderUsernameResults(resultObj, username);
}

function renderUsernameResults(usernameData, username) {
  // Handle username results (social media platforms)
  for (const [platform, info] of Object.entries(usernameData)) {
    const status = info.exists ? "success" : "warning";
    const content = `
      <div class="row align-items-center">
        <div class="col-8">
          <div class="text-muted small mb-1">Platform URL</div>
          <div class="text-truncate">
            ${info.url ? `<a href="${info.url}" target="_blank" class="text-decoration-none">${info.url}</a>` : 'N/A'}
          </div>
        </div>
        <div class="col-4 text-end">
          ${info.exists ? `
            <a class="btn btn-primary btn-sm" target="_blank" href="${info.url}">
              <i class="fas fa-external-link-alt me-1"></i>View
            </a>
          ` : '<span class="text-muted">Not found</span>'}
        </div>
      </div>
    `;
    
    const cardHtml = createModernCard(
      platform,
      "Social media platform check",
      status,
      content,
      {
        icon: "fas fa-user",
        highlighted: info.exists
      }
    );
    
    resultsGrid.insertAdjacentHTML('beforeend', cardHtml);
  }
  
  // Add Enhanced Analysis button for username results
  const enhancedAnalysisCard = `
    <div class="custom-card mb-3">
      <div class="card-body p-4 text-center">
        <h6 class="text-primary mb-3">
          <i class="fas fa-microscope me-2"></i>
          Enhanced Analysis Available
        </h6>
        <p class="text-muted mb-3">Get deeper insights with our advanced social media analysis engine</p>
        <button class="btn btn-success btn-lg" onclick="runEnhancedAnalysis('${username}')" style="border-radius: 0.75rem;">
          <i class="fas fa-search-plus me-2"></i>Run Enhanced Analysis
        </button>
      </div>
    </div>
  `;
  resultsGrid.insertAdjacentHTML('beforeend', enhancedAnalysisCard);
}

function renderEnhancedUsernameResults(resultObj) {
  const enhancedCheck = resultObj.enhanced_check;
  
  if (!enhancedCheck.username) {
    const card = el("div", "card card-platform p-2 shadow-sm");
    const body = el("div", "card-body p-2");
    body.innerHTML = `<div class="text-danger"><i class="fa-solid fa-exclamation-triangle"></i> Enhanced analysis failed</div>`;
    card.appendChild(body);
    resultsGrid.appendChild(card);
    return;
  }
  
  const data = enhancedCheck;
  
  // Investigation Summary Card
  const summaryCard = el("div", "card card-platform p-2 shadow-sm bg-light");
  const summaryBody = el("div", "card-body p-2");
  const summaryRow = el("div", "d-flex justify-content-between align-items-start");
  const summaryLeft = el("div", "");
  summaryLeft.innerHTML = `<div style="font-weight:600">📊 Investigation Summary</div>
                           <div class="text-muted" style="font-size:0.85rem">Enhanced social media analysis results</div>`;
  const summaryRight = el("div", "");
  summaryRight.innerHTML = `<div class="result-yes"><i class="fa-solid fa-chart-line"></i> Analysis Complete</div>
                            <div class="text-muted mt-2" style="font-size: 0.9rem;">
                              <strong>Found:</strong> ${data.investigation_summary.platforms_found}/${data.investigation_summary.total_platforms_checked} platforms<br>
                              <strong>Patterns:</strong> ${data.investigation_summary.correlation_patterns} correlations<br>
                              <strong>Username:</strong> ${data.username}
                            </div>`;
  summaryRow.appendChild(summaryLeft);
  summaryRow.appendChild(summaryRight);
  summaryBody.appendChild(summaryRow);
  summaryCard.appendChild(summaryBody);
  resultsGrid.appendChild(summaryCard);

  // Add Export Button
  const exportButton = el("button", "btn btn-primary mt-2 mb-3");
  exportButton.innerHTML = '<i class="fa-solid fa-download"></i> Export Results';
  exportButton.style.cssText = 'width: 100%; background: linear-gradient(45deg, #28a745, #20c997); border: none;';
  exportButton.onclick = () => exportResult(data, 'username', data.username);
  resultsGrid.appendChild(exportButton);
  
  // Enhanced Platform Results
  for (const [platform, info] of Object.entries(data.platform_results)) {
    const card = el("div", "card card-platform p-2 shadow-sm");
    const body = el("div", "card-body p-2");
    const row = el("div", "d-flex justify-content-between align-items-start");
    const left = el("div", "");
    left.innerHTML = `<div style="font-weight:600">${platform}</div>
                      <div class="text-muted" style="font-size:0.85rem">${info.url || 'N/A'}</div>`;
    const right = el("div", "");
    
    if (info.exists) {
      const engagement = info.engagement_metrics || {};
      const accountAge = info.account_age || {};
      
      right.innerHTML = `<div class="result-yes"><i class="fa-solid fa-check-circle"></i> Found + Enhanced Data</div>
                         <div class="text-muted mt-2" style="font-size: 0.85rem;">
                           ${accountAge.estimated_creation ? `<strong>📅 Est. Created:</strong> ${accountAge.estimated_creation}<br>` : ''}
                           ${engagement.estimated_followers ? `<strong>👥 Est. Followers:</strong> ${engagement.estimated_followers.toLocaleString()}<br>` : ''}
                           ${engagement.activity_level ? `<strong>📈 Activity:</strong> ${engagement.activity_level}<br>` : ''}
                           <a class="btn btn-sm btn-outline-primary mt-1" target="_blank" href="${info.url}">
                             <i class="fa-solid fa-arrow-up-right-from-square"></i> Visit
                           </a>
                         </div>`;
    } else {
      right.innerHTML = `<div class="result-no"><i class="fa-regular fa-circle-xmark"></i> Not found</div>`;
    }
    
    row.appendChild(left);
    row.appendChild(right);
    body.appendChild(row);
    card.appendChild(body);
    resultsGrid.appendChild(card);
  }
  
  // Cross-Platform Correlation Analysis
  if (data.cross_platform_analysis && data.cross_platform_analysis.length > 0) {
    const correlationCard = el("div", "card card-platform p-2 shadow-sm");
    const correlationBody = el("div", "card-body p-2");
    const correlationRow = el("div", "d-flex justify-content-between align-items-start");
    const correlationLeft = el("div", "");
    correlationLeft.innerHTML = `<div style="font-weight:600">🔗 Cross-Platform Analysis</div>
                                 <div class="text-muted" style="font-size:0.85rem">Username patterns and correlations</div>`;
    const correlationRight = el("div", "");
    
    const correlationsHtml = data.cross_platform_analysis.map(corr => `
      <div class="mb-2">
        <strong>${corr.pattern}:</strong> ${corr.description}<br>
        <div class="mt-1">
          ${corr.suggestions.map(s => `<span class="badge bg-info text-dark me-1">${s}</span>`).join('')}
        </div>
      </div>
    `).join('');
    
    correlationRight.innerHTML = `<div class="result-yes"><i class="fa-solid fa-project-diagram"></i> ${data.cross_platform_analysis.length} Patterns</div>
                                  <div class="text-muted mt-2" style="font-size: 0.85rem;">
                                    ${correlationsHtml}
                                  </div>`;
    
    correlationRow.appendChild(correlationLeft);
    correlationRow.appendChild(correlationRight);
    correlationBody.appendChild(correlationRow);
    correlationCard.appendChild(correlationBody);
    resultsGrid.appendChild(correlationCard);
  }
}

function renderEmailResults(resultObj) {
  const emailCheck = resultObj.email_check;
  
  if (!emailCheck.ok) {
    // Show error
    const card = el("div", "card card-platform p-2 shadow-sm");
    const body = el("div", "card-body p-2");
    body.innerHTML = `<div class="text-danger"><i class="fa-solid fa-exclamation-triangle"></i> ${emailCheck.error}</div>`;
    card.appendChild(body);
    resultsGrid.appendChild(card);
    return;
  }
  
  const data = emailCheck.data;
  
  // Main Email Overview Card
  const overviewCard = el("div", "card card-platform p-2 shadow-sm");
  const overviewBody = el("div", "card-body p-2");
  const overviewRow = el("div", "d-flex justify-content-between align-items-start");
  const overviewLeft = el("div", "");
  overviewLeft.innerHTML = `<div style="font-weight:600">📧 Enhanced Email Investigation</div>
                           <div class="text-muted" style="font-size:0.85rem">Comprehensive OSINT analysis</div>`;
  const overviewRight = el("div", "");
  
  let overviewInfo = `<div class="result-yes"><i class="fa-solid fa-check-circle"></i> Valid Email Format</div>`;
  overviewInfo += `<div class="text-muted mt-2" style="font-size: 0.9rem;">
                    <strong>📧 Email:</strong> ${data.email}<br>
                    <strong>👤 Local:</strong> ${data.local_part}<br>
                    <strong>🌐 Domain:</strong> ${data.domain}`;
  
  // Add validation sources badge
  if (data.validation_sources && data.validation_sources.length > 0) {
    overviewInfo += `<br><div class="mt-2">
                      <small class="badge bg-info me-1">Sources: ${data.validation_sources.slice(0, 3).join(', ')}</small>
                    </div>`;
  }
  overviewInfo += `</div>`;
  
  overviewRight.innerHTML = overviewInfo;
  overviewRow.appendChild(overviewLeft);
  overviewRow.appendChild(overviewRight);
  overviewBody.appendChild(overviewRow);
  overviewCard.appendChild(overviewBody);
  resultsGrid.appendChild(overviewCard);
  
  // Enhanced Domain Analysis Card
  if (data.domain_analysis) {
    const domainCard = el("div", "card card-platform p-2 shadow-sm");
    const domainBody = el("div", "card-body p-2");
    const domainToggle = el("div", "d-flex justify-content-between align-items-center cursor-pointer");
    domainToggle.setAttribute("data-bs-toggle", "collapse");
    domainToggle.setAttribute("data-bs-target", "#domainDetails");
    
    const domainLeft = el("div", "");
    domainLeft.innerHTML = `<div style="font-weight:600">🌐 Domain Analysis</div>
                           <div class="text-muted" style="font-size:0.85rem">Provider type and security analysis</div>`;
    
    const domainRight = el("div", "");
    const domainData = data.domain_analysis;
    const providerType = domainData.provider_type || 'Unknown';
    const reputation = domainData.domain_reputation || 'Unknown';
    
    let domainStatus = '';
    if (domainData.is_disposable) {
      domainStatus = `<div class="result-no"><i class="fa-solid fa-exclamation-triangle"></i> Disposable Email</div>`;
    } else if (domainData.is_educational) {
      domainStatus = `<div class="result-yes"><i class="fa-solid fa-graduation-cap"></i> Educational Domain</div>`;
    } else if (domainData.is_government) {
      domainStatus = `<div class="result-yes"><i class="fa-solid fa-landmark"></i> Government Domain</div>`;
    } else if (domainData.is_corporate) {
      domainStatus = `<div class="result-yes"><i class="fa-solid fa-building"></i> Corporate Domain</div>`;
    } else {
      domainStatus = `<div class="result-maybe"><i class="fa-solid fa-info-circle"></i> Personal Domain</div>`;
    }
    
    domainRight.innerHTML = domainStatus + 
                           `<div class="text-muted mt-1" style="font-size: 0.85rem;">
                             <i class="fa-solid fa-chevron-down"></i> Click for details
                           </div>`;
    
    domainToggle.appendChild(domainLeft);
    domainToggle.appendChild(domainRight);
    domainBody.appendChild(domainToggle);
    
    // Collapsible domain details
    const domainDetails = el("div", "collapse mt-3");
    domainDetails.id = "domainDetails";
    domainDetails.innerHTML = `
      <div class="bg-light p-2 rounded" style="font-size: 0.9rem;">
        <strong>Provider Type:</strong> ${providerType}<br>
        <strong>Reputation:</strong> ${reputation}<br>
        <strong>Mail Service:</strong> ${domainData.has_mail_service ? 'Active' : 'Unknown'}<br>
        <strong>Disposable:</strong> ${domainData.is_disposable ? 'Yes' : 'No'}<br>
        <strong>Educational:</strong> ${domainData.is_educational ? 'Yes' : 'No'}<br>
        <strong>Government:</strong> ${domainData.is_government ? 'Yes' : 'No'}<br>
        <strong>Corporate:</strong> ${domainData.is_corporate ? 'Yes' : 'No'}
      </div>`;
    domainBody.appendChild(domainDetails);
    domainCard.appendChild(domainBody);
    resultsGrid.appendChild(domainCard);
  }
  
  // Risk Assessment Card
  if (data.risk_assessment) {
    const riskCard = el("div", "card card-platform p-2 shadow-sm");
    const riskBody = el("div", "card-body p-2");
    const riskRow = el("div", "d-flex justify-content-between align-items-start");
    const riskLeft = el("div", "");
    riskLeft.innerHTML = `<div style="font-weight:600">⚠️ Risk Assessment</div>
                         <div class="text-muted" style="font-size:0.85rem">Security and trust analysis</div>`;
    
    const riskRight = el("div", "");
    const riskData = data.risk_assessment;
    const riskLevel = riskData.risk_level || 'Unknown';
    const trustScore = riskData.trust_score || 0;
    
    let riskColor = 'result-yes';
    let riskIcon = 'shield-check';
    if (riskLevel === 'High') {
      riskColor = 'result-no';
      riskIcon = 'exclamation-triangle';
    } else if (riskLevel === 'Medium') {
      riskColor = 'result-maybe';
      riskIcon = 'exclamation-circle';
    }
    
    let riskInfo = `<div class="${riskColor}"><i class="fa-solid fa-${riskIcon}"></i> ${riskLevel} Risk</div>`;
    riskInfo += `<div class="text-muted mt-2" style="font-size: 0.9rem;">
                  <strong>Trust Score:</strong> ${trustScore}%<br>`;
    
    if (riskData.risk_factors && riskData.risk_factors.length > 0) {
      riskInfo += `<strong>Risk Factors:</strong><br>`;
      riskData.risk_factors.slice(0, 3).forEach(factor => {
        riskInfo += `• ${factor}<br>`;
      });
    }
    riskInfo += `</div>`;
    
    riskRight.innerHTML = riskInfo;
    riskRow.appendChild(riskLeft);
    riskRow.appendChild(riskRight);
    riskBody.appendChild(riskRow);
    riskCard.appendChild(riskBody);
    resultsGrid.appendChild(riskCard);
  }
  
  // Enhanced Social Media Presence Card
  if (data.social_media_presence) {
    const socialCard = el("div", "card card-platform p-2 shadow-sm");
    const socialBody = el("div", "card-body p-2");
    const socialToggle = el("div", "d-flex justify-content-between align-items-center cursor-pointer");
    socialToggle.setAttribute("data-bs-toggle", "collapse");
    socialToggle.setAttribute("data-bs-target", "#socialDetails");
    
    const socialLeft = el("div", "");
    socialLeft.innerHTML = `<div style="font-weight:600">👤 Social Media Analysis</div>
                           <div class="text-muted" style="font-size:0.85rem">Profile discovery and association</div>`;
    
    const socialRight = el("div", "");
    const socialData = data.social_media_presence;
    const gravatarFound = socialData.gravatar && socialData.gravatar.found;
    
    let socialStatus = '';
    if (gravatarFound) {
      socialStatus = `<div class="result-yes"><i class="fa-solid fa-check-circle"></i> Gravatar Found</div>`;
    } else {
      socialStatus = `<div class="result-no"><i class="fa-regular fa-circle-xmark"></i> No Gravatar</div>`;
    }
    
    socialRight.innerHTML = socialStatus + 
                           `<div class="text-muted mt-1" style="font-size: 0.85rem;">
                             <i class="fa-solid fa-chevron-down"></i> Click for details
                           </div>`;
    
    socialToggle.appendChild(socialLeft);
    socialToggle.appendChild(socialRight);
    socialBody.appendChild(socialToggle);
    
    // Collapsible social details
    const socialDetails = el("div", "collapse mt-3");
    socialDetails.id = "socialDetails";
    
    let socialDetailsContent = `<div class="bg-light p-2 rounded" style="font-size: 0.9rem;">`;
    
    // Gravatar info
    if (gravatarFound) {
      socialDetailsContent += `<strong>Gravatar:</strong> <a href="${socialData.gravatar.profile_url}" target="_blank" class="btn btn-sm btn-outline-primary ms-2">View Profile</a><br>`;
    }
    
    // Username variations
    if (socialData.username_variations && socialData.username_variations.length > 0) {
      socialDetailsContent += `<strong>Username Variations:</strong> ${socialData.username_variations.slice(0, 3).join(', ')}<br>`;
    }
    
    // Platform likelihood
    if (socialData.platform_likely_presence) {
      socialDetailsContent += `<strong>Platform Presence Likelihood:</strong><br>`;
      Object.entries(socialData.platform_likely_presence).slice(0, 4).forEach(([platform, info]) => {
        const confidence = info.confidence || 'Unknown';
        const likely = info.likely ? '✓' : '✗';
        socialDetailsContent += `${likely} ${platform} (${confidence})<br>`;
      });
    }
    
    socialDetailsContent += `</div>`;
    socialDetails.innerHTML = socialDetailsContent;
    socialBody.appendChild(socialDetails);
    socialCard.appendChild(socialBody);
    resultsGrid.appendChild(socialCard);
  }
  
  // Breach Intelligence Card
  if (data.breach_intelligence) {
    const breachCard = el("div", "card card-platform p-2 shadow-sm");
    const breachBody = el("div", "card-body p-2");
    const breachRow = el("div", "d-flex justify-content-between align-items-start");
    const breachLeft = el("div", "");
    breachLeft.innerHTML = `<div style="font-weight:600">🔒 Breach Intelligence</div>
                           <div class="text-muted" style="font-size:0.85rem">Data breach exposure analysis</div>`;
    
    const breachRight = el("div", "");
    const breachData = data.breach_intelligence;
    const riskLevel = breachData.estimated_breach_risk || 'Unknown';
    
    let breachColor = 'result-yes';
    let breachIcon = 'shield-check';
    if (riskLevel === 'High') {
      breachColor = 'result-no';
      breachIcon = 'exclamation-triangle';
    } else if (riskLevel === 'Medium') {
      breachColor = 'result-maybe';
      breachIcon = 'exclamation-circle';
    }
    
    let breachInfo = `<div class="${breachColor}"><i class="fa-solid fa-${breachIcon}"></i> ${riskLevel} Risk</div>`;
    breachInfo += `<div class="text-muted mt-2" style="font-size: 0.9rem;">`;
    
    if (breachData.common_breach_sources && breachData.common_breach_sources.length > 0) {
      breachInfo += `<strong>Common Sources:</strong><br>`;
      breachData.common_breach_sources.slice(0, 3).forEach(source => {
        breachInfo += `• ${source}<br>`;
      });
    }
    
    breachInfo += `<small>${breachData.breach_analysis || 'Analysis not available'}</small>`;
    breachInfo += `</div>`;
    
    breachRight.innerHTML = breachInfo;
    breachRow.appendChild(breachLeft);
    breachRow.appendChild(breachRight);
    breachBody.appendChild(breachRow);
    breachCard.appendChild(breachBody);
    resultsGrid.appendChild(breachCard);
  }
  
  // Professional Analysis Card
  if (data.professional_analysis) {
    const profCard = el("div", "card card-platform p-2 shadow-sm");
    const profBody = el("div", "card-body p-2");
    const profRow = el("div", "d-flex justify-content-between align-items-start");
    const profLeft = el("div", "");
    profLeft.innerHTML = `<div style="font-weight:600">💼 Professional Analysis</div>
                         <div class="text-muted" style="font-size:0.85rem">Business and contact classification</div>`;
    
    const profRight = el("div", "");
    const profData = data.professional_analysis;
    const contactType = profData.contact_type || 'Unknown';
    const businessLikelihood = profData.business_likelihood || 'Unknown';
    
    let profStatus = '';
    if (profData.is_corporate || profData.is_educational || profData.is_government) {
      profStatus = `<div class="result-yes"><i class="fa-solid fa-building"></i> Business Email</div>`;
    } else {
      profStatus = `<div class="result-maybe"><i class="fa-solid fa-user"></i> Personal Email</div>`;
    }
    
    profStatus += `<div class="text-muted mt-2" style="font-size: 0.9rem;">
                    <strong>Contact Type:</strong> ${contactType}<br>
                    <strong>Business Likelihood:</strong> ${businessLikelihood}<br>
                    <strong>Likely Role:</strong> ${profData.likely_role || 'Unknown'}
                  </div>`;
    
    profRight.innerHTML = profStatus;
    profRow.appendChild(profLeft);
    profRow.appendChild(profRight);
    profBody.appendChild(profRow);
    profCard.appendChild(profBody);
    resultsGrid.appendChild(profCard);
  }
  
  // OSINT Search URLs Card
  if (data.osint_search_urls) {
    const osintCard = el("div", "card card-platform p-2 shadow-sm");
    const osintBody = el("div", "card-body p-2");
    const osintToggle = el("div", "d-flex justify-content-between align-items-center cursor-pointer");
    osintToggle.setAttribute("data-bs-toggle", "collapse");
    osintToggle.setAttribute("data-bs-target", "#osintUrls");
    
    const osintLeft = el("div", "");
    osintLeft.innerHTML = `<div style="font-weight:600">🔍 OSINT Search URLs</div>
                          <div class="text-muted" style="font-size:0.85rem">Comprehensive investigation resources</div>`;
    
    const osintRight = el("div", "");
    osintRight.innerHTML = `<div class="result-yes"><i class="fa-solid fa-external-link-alt"></i> Search Resources Available</div>
                           <div class="text-muted mt-1" style="font-size: 0.85rem;">
                             <i class="fa-solid fa-chevron-down"></i> Click to view URLs
                           </div>`;
    
    osintToggle.appendChild(osintLeft);
    osintToggle.appendChild(osintRight);
    osintBody.appendChild(osintToggle);
    
    // Collapsible OSINT URLs
    const osintDetails = el("div", "collapse mt-3");
    osintDetails.id = "osintUrls";
    
    let osintContent = `<div class="bg-light p-2 rounded" style="font-size: 0.9rem;">`;
    const osintData = data.osint_search_urls;
    
    // Email search URLs
    if (osintData.email_search) {
      osintContent += `<strong>🔍 Email Search:</strong><br>`;
      Object.entries(osintData.email_search).forEach(([engine, url]) => {
        osintContent += `<a href="${url}" target="_blank" class="btn btn-sm btn-outline-primary me-2 mb-1">${engine.charAt(0).toUpperCase() + engine.slice(1)}</a>`;
      });
      osintContent += `<br><br>`;
    }
    
    // Breach check URLs
    if (osintData.breach_check) {
      osintContent += `<strong>🔒 Breach Check:</strong><br>`;
      Object.entries(osintData.breach_check).slice(0, 3).forEach(([service, url]) => {
        osintContent += `<a href="${url}" target="_blank" class="btn btn-sm btn-outline-danger me-2 mb-1">${service.charAt(0).toUpperCase() + service.slice(1)}</a>`;
      });
      osintContent += `<br><br>`;
    }
    
    // Domain analysis URLs
    if (osintData.domain_analysis) {
      osintContent += `<strong>🌐 Domain Analysis:</strong><br>`;
      Object.entries(osintData.domain_analysis).slice(0, 3).forEach(([service, url]) => {
        osintContent += `<a href="${url}" target="_blank" class="btn btn-sm btn-outline-info me-2 mb-1">${service.charAt(0).toUpperCase() + service.slice(1)}</a>`;
      });
    }
    
    osintContent += `</div>`;
    osintDetails.innerHTML = osintContent;
    osintBody.appendChild(osintDetails);
    osintCard.appendChild(osintBody);
    resultsGrid.appendChild(osintCard);
  }

  // Add Export Button
  const exportButton = el("button", "btn btn-primary mt-2 mb-3");
  exportButton.innerHTML = '<i class="fa-solid fa-download"></i> Export Results';
  exportButton.style.cssText = 'width: 100%; background: linear-gradient(45deg, #007bff, #0056b3); border: none;';
  exportButton.onclick = () => exportResult(data, 'email', data.email);
  resultsGrid.appendChild(exportButton);
}

function renderPhoneResults(resultObj) {
  const phoneCheck = resultObj.phone_check;
  
  const card = el("div", "card card-platform p-2 shadow-sm");
  const body = el("div", "card-body p-2");
  const row = el("div", "d-flex justify-content-between align-items-start");
  const left = el("div", "");
  left.innerHTML = `<div style="font-weight:600">📞 Enhanced Phone Investigation</div>
                    <div class="text-muted" style="font-size:0.85rem">Multi-source phone analysis & OSINT</div>`;
  const right = el("div", "");
  
  if (phoneCheck.ok && phoneCheck.data && phoneCheck.data.valid !== false) {
    const data = phoneCheck.data;
    
    // Main validation info
    let mainInfo = `<div class="result-yes"><i class="fa-solid fa-check-circle"></i> Valid Number</div>`;
    
    // Basic details
    if (data.country_name || data.location || data.carrier || data.line_type) {
      mainInfo += `<div class="text-muted mt-2" style="font-size: 0.9rem;">
                     <strong>🌍 Country:</strong> ${data.country_name || 'Unknown'}<br>
                     <strong>📍 Location:</strong> ${data.location || 'Unknown'}<br>
                     <strong>📡 Carrier:</strong> ${data.carrier || 'Unknown'}<br>
                     <strong>📱 Type:</strong> ${data.line_type || 'Unknown'}<br>
                     <strong>🔢 Format:</strong> ${data.international_format || 'N/A'}`;
      
      // Additional Indian-specific details
      if (data.circle) {
        mainInfo += `<br><strong>� Circle:</strong> ${data.circle}`;
      }
      if (data.operator_type) {
        mainInfo += `<br><strong>📶 Network:</strong> ${data.operator_type}`;
      }
      
      mainInfo += `</div>`;
    }
    
    // Validation sources
    if (data.validation_sources && data.validation_sources.length > 0) {
      mainInfo += `<div class="mt-2">
                     <small class="badge bg-info me-1">Sources: ${data.validation_sources.join(', ')}</small>
                   </div>`;
    }
    
    // Risk assessment
    if (data.risk_assessment && data.risk_assessment.risk_level) {
      const riskColor = data.risk_assessment.risk_level === 'Low' ? 'success' : 
                       data.risk_assessment.risk_level === 'Medium' ? 'warning' : 'danger';
      mainInfo += `<div class="mt-2">
                     <small class="badge bg-${riskColor}">Risk: ${data.risk_assessment.risk_level}</small>
                     <small class="badge bg-secondary ms-1">Trust: ${data.risk_assessment.trust_score}%</small>
                   </div>`;
    }
    
    right.innerHTML = mainInfo;
    
    // Create collapsible sections for additional data
    if (data.social_media_links || data.additional_data || data.risk_assessment) {
      const detailsSection = el("div", "mt-3");
      
      // Social Media Links
      if (data.social_media_links && data.social_media_links.length > 0) {
        const socialCard = el("div", "card mt-2");
        socialCard.innerHTML = `
          <div class="card-header py-1">
            <h6 class="mb-0">
              <button class="btn btn-link btn-sm p-0 text-decoration-none" type="button" data-bs-toggle="collapse" data-bs-target="#social-${Date.now()}">
                🌐 Social Media Associations
              </button>
            </h6>
          </div>
          <div class="collapse" id="social-${Date.now()}">
            <div class="card-body py-2">
              ${data.social_media_links.map(platform => 
                `<div class="mb-1">
                   <strong>${platform.name}:</strong> 
                   <a href="${platform.url}" target="_blank" class="text-decoration-none">${platform.likely ? '✅ Likely' : '❓ Check'}</a>
                 </div>`
              ).join('')}
            </div>
          </div>
        `;
        detailsSection.appendChild(socialCard);
      }
      
      // OSINT Search URLs
      if (data.additional_data && data.additional_data.search_urls) {
        const osintCard = el("div", "card mt-2");
        const urls = data.additional_data.search_urls;
        osintCard.innerHTML = `
          <div class="card-header py-1">
            <h6 class="mb-0">
              <button class="btn btn-link btn-sm p-0 text-decoration-none" type="button" data-bs-toggle="collapse" data-bs-target="#osint-${Date.now()}">
                🔍 OSINT Search Links
              </button>
            </h6>
          </div>
          <div class="collapse" id="osint-${Date.now()}">
            <div class="card-body py-2">
              <div class="row">
                <div class="col-md-6">
                  <strong>Phone Lookup:</strong><br>
                  <a href="${urls.truecaller_search}" target="_blank" class="d-block">TrueCaller</a>
                  <a href="${urls.whocalld_search}" target="_blank" class="d-block">WhoCalld</a>
                  <a href="${urls.phonevalidator}" target="_blank" class="d-block">PhoneValidator</a>
                </div>
                <div class="col-md-6">
                  <strong>Social Search:</strong><br>
                  <a href="${urls.google_search}" target="_blank" class="d-block">Google Search</a>
                  <a href="${urls.facebook_search}" target="_blank" class="d-block">Facebook</a>
                  <a href="${urls.linkedin_search}" target="_blank" class="d-block">LinkedIn</a>
                </div>
              </div>
            </div>
          </div>
        `;
        detailsSection.appendChild(osintCard);
      }
      
      // Search Variations
      if (data.additional_data && data.additional_data.search_variations) {
        const variationsCard = el("div", "card mt-2");
        variationsCard.innerHTML = `
          <div class="card-header py-1">
            <h6 class="mb-0">
              <button class="btn btn-link btn-sm p-0 text-decoration-none" type="button" data-bs-toggle="collapse" data-bs-target="#variations-${Date.now()}">
                🔢 Number Variations
              </button>
            </h6>
          </div>
          <div class="collapse" id="variations-${Date.now()}">
            <div class="card-body py-2">
              ${data.additional_data.search_variations.map(variation => 
                `<code class="me-2">${variation}</code>`
              ).join('')}
            </div>
          </div>
        `;
        detailsSection.appendChild(variationsCard);
      }
      
      // Risk Assessment Details
      if (data.risk_assessment && data.risk_assessment.risk_factors && data.risk_assessment.risk_factors.length > 0) {
        const riskCard = el("div", "card mt-2");
        riskCard.innerHTML = `
          <div class="card-header py-1">
            <h6 class="mb-0">
              <button class="btn btn-link btn-sm p-0 text-decoration-none" type="button" data-bs-toggle="collapse" data-bs-target="#risk-${Date.now()}">
                ⚠️ Risk Assessment
              </button>
            </h6>
          </div>
          <div class="collapse" id="risk-${Date.now()}">
            <div class="card-body py-2">
              <strong>Risk Factors:</strong><br>
              ${data.risk_assessment.risk_factors.map(factor => `• ${factor}`).join('<br>')}
              ${data.risk_assessment.recommendations ? 
                `<br><br><strong>Recommendations:</strong><br>${data.risk_assessment.recommendations.map(rec => `• ${rec}`).join('<br>')}` : ''}
            </div>
          </div>
        `;
        detailsSection.appendChild(riskCard);
      }
      
      body.appendChild(detailsSection);
    }
    
  } else {
    // Validation failed or error
    const errorMsg = phoneCheck.error || 'Validation failed';
    right.innerHTML = `<div class="result-no"><i class="fa-solid fa-exclamation-triangle"></i> ${phoneCheck.ok ? 'Invalid' : 'Error'}</div>
                       <div class="text-muted mt-2"><small>${errorMsg}</small></div>`;
  }
  
  row.appendChild(left);
  row.appendChild(right);
  body.appendChild(row);
  card.appendChild(body);
  resultsGrid.appendChild(card);

  // Add Export Button
  const exportButton = el("button", "btn btn-primary mt-2 mb-3");
  exportButton.innerHTML = '<i class="fa-solid fa-download"></i> Export Results';
  exportButton.style.cssText = 'width: 100%; background: linear-gradient(45deg, #17a2b8, #138496); border: none;';
  exportButton.onclick = () => exportResult(phoneCheck.data || {}, 'phone', phoneCheck.data?.number || phoneCheck.data?.international_format || 'unknown');
  resultsGrid.appendChild(exportButton);
}

function renderIPResults(resultObj) {
  let data;
  
  // Handle different data structures
  if (resultObj.ip_check) {
    if (!resultObj.ip_check.ok) {
      // Show error
      const card = el("div", "card card-platform p-2 shadow-sm");
      const body = el("div", "card-body p-2");
      body.innerHTML = `<div class="text-danger"><i class="fa-solid fa-exclamation-triangle"></i> ${resultObj.ip_check.error}</div>`;
      card.appendChild(body);
      resultsGrid.appendChild(card);
      return;
    }
    data = resultObj.ip_check.data;
  } else {
    // Direct data format
    data = resultObj;
  }
  
  // Main IP Overview Card
  const overviewCard = el("div", "card card-platform p-2 shadow-sm");
  const overviewBody = el("div", "card-body p-2");
  const overviewRow = el("div", "d-flex justify-content-between align-items-start");
  const overviewLeft = el("div", "");
  overviewLeft.innerHTML = `<div style="font-weight:600">🌐 Enhanced IP Investigation</div>
                           <div class="text-muted" style="font-size:0.85rem">Comprehensive OSINT analysis</div>`;
  const overviewRight = el("div", "");
  
  let overviewInfo = `<div class="result-yes"><i class="fa-solid fa-check-circle"></i> Valid IP Address</div>`;
  overviewInfo += `<div class="text-muted mt-2" style="font-size: 0.9rem;">
                    <strong>🌐 IP:</strong> ${data.ip || 'Unknown'}<br>
                    <strong>🔒 Type:</strong> ${data.is_private ? 'Private/Internal' : 'Public'}<br>
                    <strong>📍 Location:</strong> ${data.geolocation?.city || 'Unknown'}, ${data.geolocation?.country || 'Unknown'}`;
  
  if (data.geolocation?.isp) {
    overviewInfo += `<br><strong>🏢 ISP:</strong> ${data.geolocation.isp}`;
  }
  
  overviewInfo += `</div>`;
  
  overviewRight.innerHTML = overviewInfo;
  overviewRow.appendChild(overviewLeft);
  overviewRow.appendChild(overviewRight);
  overviewBody.appendChild(overviewRow);
  overviewCard.appendChild(overviewBody);
  resultsGrid.appendChild(overviewCard);
  
  // Render detailed IP information
  const sections = [
    { title: "📍 Geolocation", data: data.geolocation, icon: "fa-map-marker-alt" },
    { title: "🌐 Network Info", data: data.network_info, icon: "fa-network-wired" },
    { title: "🔍 Reverse DNS", data: data.reverse_dns, icon: "fa-search" },
    { title: "🛡️ Security Analysis", data: data.security_analysis, icon: "fa-shield-alt" },
    { title: "⭐ Reputation", data: data.reputation, icon: "fa-star" },
    { title: "🔗 OSINT URLs", data: data.osint_search_urls, icon: "fa-external-link-alt" },
    { title: "⚠️ Threat Intelligence", data: data.threat_intelligence, icon: "fa-exclamation-triangle" },
    { title: "ℹ️ Additional Info", data: data.additional_info, icon: "fa-info-circle" }
  ];
  
  sections.forEach(section => {
    if (section.data && Object.keys(section.data).length > 0) {
      const card = el("div", "card card-platform p-2 shadow-sm");
      const body = el("div", "card-body p-2");
      const row = el("div", "d-flex justify-content-between align-items-start");
      const left = el("div", "");
      left.innerHTML = `<div style="font-weight:600"><i class="fa-solid ${section.icon}"></i> ${section.title}</div>`;
      
      const right = el("div", "");
      let content = '';
      
      if (section.title === "🔗 OSINT URLs") {
        // Special handling for OSINT URLs
        content = '<div class="row g-2">';
        let count = 0;
        for (const [platform, url] of Object.entries(section.data)) {
          if (count < 8) { // Show only first 8 URLs
            content += `<div class="col-6"><a href="${url}" target="_blank" class="btn btn-sm btn-outline-primary w-100">${platform}</a></div>`;
            count++;
          }
        }
        content += '</div>';
        if (Object.keys(section.data).length > 8) {
          content += `<small class="text-muted">... and ${Object.keys(section.data).length - 8} more URLs</small>`;
        }
      } else {
        // Regular data display
        for (const [key, value] of Object.entries(section.data)) {
          if (value && value !== 'Unknown' && value !== 'N/A' && value !== null) {
            const displayKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            if (typeof value === 'boolean') {
              content += `<div><strong>${displayKey}:</strong> ${value ? '✅ Yes' : '❌ No'}</div>`;
            } else if (Array.isArray(value) && value.length > 0) {
              content += `<div><strong>${displayKey}:</strong> ${value.join(', ')}</div>`;
            } else if (typeof value === 'object') {
              // Skip nested objects for now
              continue;
            } else {
              content += `<div><strong>${displayKey}:</strong> ${value}</div>`;
            }
          }
        }
      }
      
      if (content) {
        right.innerHTML = content;
      } else {
        right.innerHTML = '<div class="text-muted">No additional information available</div>';
      }
      
      row.appendChild(left);
      row.appendChild(right);
      body.appendChild(row);
      card.appendChild(body);
      resultsGrid.appendChild(card);
    }
  });

  // Add Export Button
  const exportButton = el("button", "btn btn-primary mt-2 mb-3");
  exportButton.innerHTML = '<i class="fa-solid fa-download"></i> Export Results';
  exportButton.style.cssText = 'width: 100%; background: linear-gradient(45deg, #fd7e14, #e55a00); border: none;';
  exportButton.onclick = () => exportResult(data, 'ip', data.ip || 'unknown');
  resultsGrid.appendChild(exportButton);
}

function renderNameResults(resultObj) {
  const nameCheck = resultObj.name_check;
  
  if (!nameCheck.ok) {
    // Show error
    const errorContent = `
      <div class="text-danger">
        <i class="fas fa-exclamation-triangle me-2"></i>
        ${nameCheck.error}
      </div>
    `;
    const errorCard = createModernCard(
      "Investigation Error",
      "Name investigation could not be completed",
      "error",
      errorContent,
      { icon: "fas fa-exclamation-triangle" }
    );
    resultsGrid.insertAdjacentHTML('beforeend', errorCard);
    return;
  }
  
  const data = nameCheck.data;
  
  // Investigation Overview Header
  const overviewContent = `
    <div class="row align-items-center">
      <div class="col-md-8">
        <div class="mb-2">
          <span class="badge bg-primary px-3 py-2">
            <i class="fas fa-user me-2"></i>Person Investigation
          </span>
        </div>
        <h6 class="mb-1">Investigating: <strong class="text-primary">${data.name}</strong></h6>
        <p class="text-muted small mb-0">
          Found ${data.variations.length} name variations across multiple data sources
        </p>
      </div>
      <div class="col-md-4 text-end">
        <div class="text-success">
          <i class="fas fa-check-circle fs-4"></i>
        </div>
        <small class="text-muted">Investigation Complete</small>
      </div>
    </div>
  `;
  
  const overviewCard = createModernCard(
    "Name Investigation Summary",
    "Comprehensive analysis results",
    "success",
    overviewContent,
    { 
      icon: "fas fa-user-detective",
      highlighted: true
    }
  );
  resultsGrid.insertAdjacentHTML('beforeend', overviewCard);

  // Section 1: Social Profiles
  renderSocialProfilesSection(data);
  
  // Section 2: Related Links  
  renderRelatedLinksSection(data);
  
  // Section 3: Other Matches
  renderOtherMatchesSection(data);
  
  // Store data for export and create export button
  window.currentNameData = data;
  const exportButton = `
    <div class="custom-card mb-3">
      <div class="card-body p-4 text-center">
        <button class="btn btn-success btn-lg px-5" onclick="exportResult(window.currentNameData, 'name', '${data.name || 'unknown'}')" style="border-radius: 0.75rem;">
          <i class="fas fa-download me-2"></i>Export Complete Report
        </button>
      </div>
    </div>
  `;
  resultsGrid.insertAdjacentHTML('beforeend', exportButton);
}

function renderSocialProfilesSection(data) {
  // Social Profiles Section Header
  const sectionHeader = `
    <div class="row mb-4">
      <div class="col-12">
        <h5 class="text-primary mb-3">
          <i class="fas fa-users me-2"></i>Social Profiles
        </h5>
        <p class="text-muted small mb-0">Discovered social media handles and professional profiles</p>
      </div>
    </div>
  `;
  resultsGrid.insertAdjacentHTML('beforeend', `<div class="mb-4">${sectionHeader}</div>`);
  
  // Professional Networks Grid
  const professionalProfiles = data.professional_networks;
  const foundProfiles = Object.entries(professionalProfiles).filter(([_, profile]) => profile.found);
  
  if (foundProfiles.length > 0) {
    const profilesRow = document.createElement('div');
    profilesRow.className = 'row g-3 mb-4';
    
    foundProfiles.forEach(([platform, profile]) => {
      const platformIcon = getPlatformIcon(platform);
      const profileCard = `
        <div class="col-lg-6">
          <div class="custom-card h-100 profile-card" style="transition: all 0.3s ease; cursor: pointer;">
            <div class="card-body p-3">
              <div class="d-flex align-items-center">
                <div class="me-3">
                  <div class="bg-primary bg-opacity-10 rounded-circle p-3 d-flex align-items-center justify-content-center" style="width: 50px; height: 50px;">
                    <i class="${platformIcon} text-primary fs-5"></i>
                  </div>
                </div>
                <div class="flex-grow-1">
                  <h6 class="mb-1 text-primary">${platform}</h6>
                  <p class="text-muted small mb-2">Professional Profile Found</p>
                  ${profile.profiles && profile.profiles.length > 0 ? 
                    profile.profiles.map(url => 
                      `<a href="https://${url}" target="_blank" class="btn btn-outline-primary btn-sm me-2">
                        <i class="fas fa-external-link-alt me-1"></i>View Profile
                      </a>`
                    ).join('') : 
                    `<span class="badge bg-success">Profile Available</span>`
                  }
                </div>
              </div>
            </div>
          </div>
        </div>
      `;
      profilesRow.insertAdjacentHTML('beforeend', profileCard);
    });
    
    resultsGrid.appendChild(profilesRow);
  } else {
    // No profiles found
    const noProfilesCard = createModernCard(
      "No Social Profiles Found",
      "No professional network profiles discovered",
      "warning",
      `<div class="text-center py-3">
        <i class="fas fa-user-slash text-muted fs-1 mb-3"></i>
        <p class="text-muted">No profiles found on LinkedIn, AngelList, or other professional networks.</p>
        <small class="text-muted">Try searching suggested usernames manually on social platforms.</small>
      </div>`,
      { icon: "fas fa-users" }
    );
    resultsGrid.insertAdjacentHTML('beforeend', noProfilesCard);
  }
}

function renderRelatedLinksSection(data) {
  // Related Links Section Header
  const sectionHeader = `
    <div class="row mb-4 mt-5">
      <div class="col-12">
        <h5 class="text-primary mb-3">
          <i class="fas fa-link me-2"></i>Related Links
        </h5>
        <p class="text-muted small mb-0">Potential usernames and social media suggestions</p>
      </div>
    </div>
  `;
  resultsGrid.insertAdjacentHTML('beforeend', `<div class="mb-4">${sectionHeader}</div>`);
  
  // Username Suggestions Grid
  if (data.username_suggestions && data.username_suggestions.length > 0) {
    const suggestionsRow = document.createElement('div');
    suggestionsRow.className = 'row g-3 mb-4';
    
    data.username_suggestions.forEach((username, index) => {
      const suggestionCard = `
        <div class="col-lg-4 col-md-6">
          <div class="custom-card h-100 username-card" style="transition: all 0.3s ease; cursor: pointer;" onclick="searchUsername('${username}')">
            <div class="card-body p-3 text-center">
              <div class="mb-3">
                <div class="bg-info bg-opacity-10 rounded-circle p-3 d-inline-flex align-items-center justify-content-center" style="width: 50px; height: 50px;">
                  <i class="fas fa-at text-info fs-5"></i>
                </div>
              </div>
              <h6 class="mb-2 text-primary">${username}</h6>
              <p class="text-muted small mb-3">Suggested username</p>
              <div class="d-flex gap-2 justify-content-center flex-wrap">
                <a href="https://twitter.com/${username}" target="_blank" class="btn btn-outline-primary btn-sm">
                  <i class="fab fa-twitter"></i>
                </a>
                <a href="https://instagram.com/${username}" target="_blank" class="btn btn-outline-primary btn-sm">
                  <i class="fab fa-instagram"></i>
                </a>
                <a href="https://github.com/${username}" target="_blank" class="btn btn-outline-primary btn-sm">
                  <i class="fab fa-github"></i>
                </a>
                <a href="https://linkedin.com/in/${username}" target="_blank" class="btn btn-outline-primary btn-sm">
                  <i class="fab fa-linkedin"></i>
                </a>
              </div>
            </div>
          </div>
        </div>
      `;
      suggestionsRow.insertAdjacentHTML('beforeend', suggestionCard);
    });
    
    resultsGrid.appendChild(suggestionsRow);
  } else {
    // No suggestions available
    const noSuggestionsCard = createModernCard(
      "No Username Suggestions",
      "Unable to generate username variations",
      "warning", 
      `<div class="text-center py-3">
        <i class="fas fa-question-circle text-muted fs-1 mb-3"></i>
        <p class="text-muted">No username suggestions could be generated from this name.</p>
      </div>`,
      { icon: "fas fa-link" }
    );
    resultsGrid.insertAdjacentHTML('beforeend', noSuggestionsCard);
  }
}

function renderOtherMatchesSection(data) {
  // Other Matches Section Header
  const sectionHeader = `
    <div class="row mb-4 mt-5">
      <div class="col-12">
        <h5 class="text-primary mb-3">
          <i class="fas fa-database me-2"></i>Other Matches
        </h5>
        <p class="text-muted small mb-0">Public records, name variations, and additional data</p>
      </div>
    </div>
  `;
  resultsGrid.insertAdjacentHTML('beforeend', `<div class="mb-4">${sectionHeader}</div>`);
  
  const otherMatchesRow = document.createElement('div');
  otherMatchesRow.className = 'row g-3 mb-4';
  
  // Name Variations Card
  const variationsContent = `
    <div class="mb-3">
      <h6 class="text-primary mb-2">
        <i class="fas fa-list-alt me-2"></i>Name Variations
      </h6>
      <p class="text-muted small mb-3">Common name formats and variations</p>
      <div class="d-flex flex-wrap gap-2">
        ${data.variations.slice(0, 8).map(variation => 
          `<span class="badge bg-light text-dark border px-2 py-1">${variation}</span>`
        ).join('')}
        ${data.variations.length > 8 ? 
          `<span class="badge bg-secondary">+${data.variations.length - 8} more</span>` : 
          ''
        }
      </div>
    </div>
  `;
  
  const variationsCard = `
    <div class="col-lg-6">
      <div class="custom-card h-100">
        <div class="card-body p-4">
          ${variationsContent}
        </div>
      </div>
    </div>
  `;
  
  // Public Records Card
  const records = data.public_records;
  const foundRecords = Object.entries(records).filter(([key, val]) => val.found && !['variations_checked', 'name_variations'].includes(key));
  
  const recordsContent = `
    <div class="mb-3">
      <h6 class="text-primary mb-2">
        <i class="fas fa-file-alt me-2"></i>Public Records
      </h6>
      <p class="text-muted small mb-3">Government and public database searches</p>
      ${foundRecords.length > 0 ? `
        <div class="mb-3">
          ${foundRecords.map(([recordType, data]) => {
            const recordName = recordType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            return `
              <div class="d-flex align-items-center mb-2">
                <i class="fas fa-check-circle text-success me-2"></i>
                <span class="fw-medium">${recordName}</span>
              </div>
            `;
          }).join('')}
        </div>
        <div class="bg-success bg-opacity-10 border border-success border-opacity-25 rounded p-3">
          <small class="text-success fw-medium">
            <i class="fas fa-info-circle me-1"></i>
            Found ${foundRecords.length} record type(s) across ${records.variations_checked || 0} name variations
          </small>
        </div>
      ` : `
        <div class="text-center py-3">
          <i class="fas fa-file-excel text-muted fs-4 mb-2"></i>
          <p class="text-muted mb-1">No public records found</p>
          <small class="text-muted">Searched ${records.variations_checked || 0} name variations</small>
        </div>
      `}
    </div>
  `;
  
  const recordsCard = `
    <div class="col-lg-6">
      <div class="custom-card h-100">
        <div class="card-body p-4">
          ${recordsContent}
        </div>
      </div>
    </div>
  `;
  
  otherMatchesRow.insertAdjacentHTML('beforeend', variationsCard);
  otherMatchesRow.insertAdjacentHTML('beforeend', recordsCard);
  resultsGrid.appendChild(otherMatchesRow);
}

function getPlatformIcon(platform) {
  const icons = {
    'LinkedIn': 'fab fa-linkedin',
    'AngelList': 'fas fa-angel',
    'Crunchbase': 'fas fa-building',
    'ResearchGate': 'fas fa-graduation-cap',
    'GitHub': 'fab fa-github',
    'Twitter': 'fab fa-twitter',
    'Instagram': 'fab fa-instagram',
    'Facebook': 'fab fa-facebook'
  };
  return icons[platform] || 'fas fa-user';
}

function searchUsername(username) {
  // Fill the search input and trigger search
  document.getElementById('usernameInput').value = username;
  document.getElementById('searchForm').dispatchEvent(new Event('submit'));
}

async function runEnhancedAnalysis(username) {
  clearResults();
  statusArea.innerHTML = `<div class="spinner-center"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div> <div class="ms-2">Running enhanced analysis for ${username}…</div></div>`;
  
  try {
    const res = await fetch("/api/enhanced-username", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username })
    });
    const j = await res.json();
    
    if (res.ok) {
      renderResults(username, j);
      fetchHistory(); // refresh sidebar
    } else {
      statusArea.innerHTML = `<div class="text-danger">${j.error || 'Enhanced analysis failed'}</div>`;
    }
  } catch (err) {
    statusArea.innerHTML = `<div class="text-danger">Network error during enhanced analysis</div>`;
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = usernameInput.value.trim();
  if (!username) return;
  clearResults();
  statusArea.innerHTML = showLoadingSpinner(`Investigating ${username}...`);
  
  try {
    const res = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username })
    });
    const j = await res.json();
    
    if (res.ok) {
      // Show success message briefly
      statusArea.innerHTML = showSuccessAlert(`Investigation completed for ${username}`, "success");
      setTimeout(() => {
        statusArea.innerHTML = "";
      }, 3000);
      
      // Handle different response types
      if (j.type === "email") {
        renderResults(username, j);
      } else if (j.type === "phone") {
        renderResults(username, j);
      } else if (j.type === "name") {
        renderResults(username, j);
      } else if (j.type === "enhanced_username") {
        renderResults(username, j);
      } else if (j.username && j.results) {
        renderResults(j.username, j.results);
      } else {
        renderResults(username, j);
      }
      fetchHistory();
    } else {
      statusArea.innerHTML = showSuccessAlert(j.error || 'Investigation failed', "danger");
    }
  } catch (err) {
    statusArea.innerHTML = showSuccessAlert('Network error - please try again', "danger");
  }
});

async function runBulkSearch() {
  const items = bulkInput.value.trim().split('\n').filter(item => item.trim());
  const searchType = bulkType.value;
  
  if (items.length === 0) {
    statusArea.innerHTML = showSuccessAlert('Please enter at least one item to search', "warning");
    return;
  }
  
  if (items.length > 50) {
    statusArea.innerHTML = showSuccessAlert('Maximum 50 items allowed for bulk search', "warning");
    return;
  }
  
  clearResults();
  statusArea.innerHTML = showLoadingSpinner(`Processing ${items.length} items...`);
  
  try {
    const res = await fetch("/api/bulk-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, type: searchType })
    });
    const j = await res.json();
    
    if (res.ok) {
      currentBulkResults = j.bulk_results;
      
      // Show success message
      statusArea.innerHTML = showSuccessAlert(
        `Bulk search completed: ${j.summary.successful}/${j.summary.total_items} successful`, 
        "success"
      );
      setTimeout(() => {
        statusArea.innerHTML = "";
      }, 3000);
      
      renderBulkResults(j);
      exportSection.classList.remove('d-none');
      fetchHistory();
    } else {
      statusArea.innerHTML = showSuccessAlert(j.error || 'Bulk search failed', "danger");
    }
  } catch (err) {
    statusArea.innerHTML = showSuccessAlert('Network error during bulk search', "danger");
  }
}

function renderBulkResults(bulkData) {
  clearResults();
  const summary = bulkData.summary;
  
  // Summary Card
  const summaryContent = `
    <div class="row text-center">
      <div class="col-md-3">
        <div class="h4 text-primary mb-0">${summary.total_items}</div>
        <small class="text-muted">Total Items</small>
      </div>
      <div class="col-md-3">
        <div class="h4 text-success mb-0">${summary.successful}</div>
        <small class="text-muted">Successful</small>
      </div>
      <div class="col-md-3">
        <div class="h4 text-danger mb-0">${summary.failed}</div>
        <small class="text-muted">Failed</small>
      </div>
      <div class="col-md-3">
        <div class="h4 text-info mb-0">${summary.search_type}</div>
        <small class="text-muted">Search Type</small>
      </div>
    </div>
  `;
  
  const summaryCard = createModernCard(
    "Bulk Search Summary",
    `Processed ${summary.total_items} items with ${((summary.successful/summary.total_items)*100).toFixed(1)}% success rate`,
    "success",
    summaryContent,
    {
      icon: "fas fa-chart-bar",
      highlighted: true
    }
  );
  
  resultsGrid.insertAdjacentHTML('beforeend', summaryCard);
  
  // Individual Results
  bulkData.bulk_results.forEach((result, index) => {
    let details = "";
    const status = result.status === "success" ? "success" : "error";
    
    if (result.status === "success") {
      if (result.type === "username") {
        const foundPlatforms = Object.entries(result.result).filter(([_, info]) => info.exists).length;
        details = `Found on ${foundPlatforms} social media platforms`;
      } else if (result.type === "email" && result.result.ok) {
        details = `Valid email from ${result.result.data.domain}`;
      } else if (result.type === "phone" && result.result.ok) {
        details = result.result.data.valid ? `Valid number - ${result.result.data.carrier}` : "Invalid phone number";
      } else if (result.type === "name" && result.result.ok) {
        details = `Found ${result.result.data.variations.length} name variations`;
      } else {
        details = "Investigation completed successfully";
      }
    } else {
      details = result.result.error || "Investigation failed";
    }
    
    const content = `
      <div class="row align-items-center">
        <div class="col-8">
          <div class="text-muted small mb-1">Investigation Type</div>
          <div class="badge bg-secondary">${result.type}</div>
        </div>
        <div class="col-4 text-end">
          <div class="small text-muted">#${index + 1}</div>
        </div>
      </div>
      <div class="mt-2">
        <div class="text-muted small">Details</div>
        <div class="small">${details}</div>
      </div>
    `;
    
    const resultCard = createModernCard(
      result.item,
      `Investigation result for ${result.type}`,
      status,
      content,
      {
        icon: result.type === "email" ? "fas fa-envelope" : 
              result.type === "phone" ? "fas fa-phone" :
              result.type === "ip" ? "fas fa-globe" :
              result.type === "name" ? "fas fa-user" : "fas fa-at"
      }
    );
    
    resultsGrid.insertAdjacentHTML('beforeend', resultCard);
  });
}

async function exportResults(format) {
  if (!currentBulkResults) {
    alert('No results to export');
    return;
  }
  
  exportStatus.textContent = `Exporting ${format.toUpperCase()}...`;
  
  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format, results: currentBulkResults })
    });
    
    if (format === "json") {
      const jsonData = await res.json();
      const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `osint_export_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
      a.click();
      URL.revokeObjectURL(url);
      exportStatus.textContent = 'JSON exported successfully!';
    } else if (format === "csv") {
      const csvResponse = await res.text();
      const blob = new Blob([csvResponse], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `osint_export_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      exportStatus.textContent = 'CSV exported successfully!';
    }
    
    setTimeout(() => {
      exportStatus.textContent = '';
    }, 3000);
    
  } catch (err) {
    exportStatus.textContent = `Export failed: ${err.message}`;
    setTimeout(() => {
      exportStatus.textContent = '';
    }, 5000);
  }
}

// Watchlist Management Functions
async function fetchWatchlist() {
  try {
    const res = await fetch("/api/watchlist");
    const j = await res.json();
    displayWatchlist(j.watchlist || []);
  } catch (err) {
    watchlistItems.innerHTML = "<div class='text-danger small'>Failed to load watchlist</div>";
  }
}

function displayWatchlist(watchlist) {
  watchlistItems.innerHTML = "";
  
  if (watchlist.length === 0) {
    watchlistItems.innerHTML = "<div class='text-muted small'>Watchlist is empty</div>";
    return;
  }
  
  watchlist.forEach(item => {
    const row = el("div", "d-flex justify-content-between align-items-center mb-1 p-1 border rounded small");
    const typeIcon = {
      email: "fa-envelope",
      phone: "fa-phone", 
      name: "fa-user",
      username: "fa-at",
      ip: "fa-globe"
    }[item.item_type] || "fa-search";
    
    row.innerHTML = `
      <div style="flex: 1;">
        <i class="fa-solid ${typeIcon} me-1" style="color: #6c757d;"></i>
        <span>${item.item}</span>
      </div>
      <button class="btn btn-sm btn-outline-danger" onclick="removeFromWatchlistHandler('${item.item}')">
        <i class="fa-solid fa-times"></i>
      </button>
    `;
    watchlistItems.appendChild(row);
  });
}

async function addItemToWatchlist(item) {
  try {
    const res = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item })
    });
    
    if (res.ok) {
      fetchWatchlist();
      return true;
    } else {
      const j = await res.json();
      if (res.status === 409) {
        alert("Item already in watchlist");
      } else {
        alert(j.error || "Failed to add to watchlist");
      }
      return false;
    }
  } catch (err) {
    alert("Network error while adding to watchlist");
    return false;
  }
}

async function removeFromWatchlistHandler(item) {
  try {
    const res = await fetch(`/api/watchlist/${encodeURIComponent(item)}`, {
      method: "DELETE"
    });
    
    if (res.ok) {
      fetchWatchlist();
    } else {
      alert("Failed to remove from watchlist");
    }
  } catch (err) {
    alert("Network error while removing from watchlist");
  }
}

async function monitorWatchlistHandler() {
  const originalText = monitorWatchlist.innerHTML;
  monitorWatchlist.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Monitoring...';
  monitorWatchlist.disabled = true;
  
  try {
    const res = await fetch("/api/watchlist/monitor", {
      method: "POST"
    });
    const j = await res.json();
    
    if (res.ok) {
      // Display monitoring results
      clearResults();
      statusArea.innerHTML = `<h5>Watchlist Monitoring Results</h5>`;
      renderBulkResults({ bulk_results: j.monitor_results, summary: j.summary });
      fetchHistory(); // Refresh history since monitoring creates new entries
    } else {
      alert(j.error || "Monitoring failed");
    }
  } catch (err) {
    alert("Network error during monitoring");
  } finally {
    monitorWatchlist.innerHTML = originalText;
    monitorWatchlist.disabled = false;
  }
}

// Event listeners for bulk search and export
bulkSearchBtn.onclick = runBulkSearch;
exportJson.onclick = () => exportResults('json');
exportCsv.onclick = () => exportResults('csv');

// Event listeners for watchlist
addToWatchlist.onclick = async () => {
  const item = watchlistInput.value.trim();
  if (item) {
    const success = await addItemToWatchlist(item);
    if (success) {
      watchlistInput.value = "";
    }
  }
};

watchlistInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") {
    addToWatchlist.click();
  }
});

monitorWatchlist.onclick = monitorWatchlistHandler;

// Event listeners for filtering and sorting
filterBtns.forEach(btn => {
  btn.onclick = () => {
    filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    displayFilteredHistory();
  };
});

sortHistory.onchange = () => {
  currentSort = sortHistory.value;
  displayFilteredHistory();
};

clearBtn.onclick = () => {
  usernameInput.value = "";
  clearResults();
};

window.addEventListener("DOMContentLoaded", () => {
  fetchHistory();
  fetchWatchlist();
});

// Export Functions
function exportResult(resultData, investigationType, target) {
    const exportModal = document.createElement('div');
    exportModal.className = 'modal';
    exportModal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    `;

    const modalContent = document.createElement('div');
    modalContent.style.cssText = `
        background: white;
        padding: 30px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    `;

    modalContent.innerHTML = `
        <h3>Export Result</h3>
        <p>Choose export format for ${investigationType} investigation of "${target}"</p>
        <div style="margin: 20px 0;">
            <button onclick="exportResultFormat('json', '${investigationType}', '${target}')" 
                    style="margin: 5px; padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer;">
                JSON
            </button>
            <button onclick="exportResultFormat('csv', '${investigationType}', '${target}')" 
                    style="margin: 5px; padding: 10px 20px; background: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer;">
                CSV
            </button>
            <button onclick="exportResultFormat('pdf', '${investigationType}', '${target}')" 
                    style="margin: 5px; padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 5px; cursor: pointer;">
                PDF
            </button>
        </div>
        <button onclick="closeExportModal()" 
                style="margin-top: 15px; padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 5px; cursor: pointer;">
            Cancel
        </button>
    `;

    exportModal.appendChild(modalContent);
    document.body.appendChild(exportModal);

    // Store data for export
    window.currentExportData = {
        result_data: resultData,
        type: investigationType,
        target: target
    };

    // Close modal on outside click
    exportModal.addEventListener('click', function(e) {
        if (e.target === exportModal) {
            closeExportModal();
        }
    });
}

function exportResultFormat(format, investigationType, target) {
    if (!window.currentExportData) {
        alert('No data to export');
        return;
    }

    // Show loading
    const loadingDiv = document.createElement('div');
    loadingDiv.innerHTML = `
        <div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); 
                    background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); z-index: 1001;">
            <div style="text-align: center;">
                <div style="margin-bottom: 10px;">Generating ${format.toUpperCase()} export...</div>
                <div style="width: 30px; height: 30px; border: 3px solid #f3f3f3; border-top: 3px solid #3498db; 
                           border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto;"></div>
            </div>
        </div>
        <style>
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    `;
    document.body.appendChild(loadingDiv);

    fetch('/api/export-result', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            ...window.currentExportData,
            format: format
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => Promise.reject(err));
        }
        
        // Get filename from response headers
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `osint_${investigationType}_${target}_${new Date().toISOString().slice(0,19).replace(/:/g, '-')}.${format}`;
        
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]*)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        return response.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => {
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        // Remove loading and close modal
        document.body.removeChild(loadingDiv);
        closeExportModal();
        
        // Show success message
        showNotification(`${format.toUpperCase()} export downloaded successfully!`, 'success');
    })
    .catch(error => {
        document.body.removeChild(loadingDiv);
        console.error('Export error:', error);
        alert(error.error || `Failed to export ${format.toUpperCase()}`);
    });
}

function closeExportModal() {
    const modal = document.querySelector('.modal');
    if (modal) {
        document.body.removeChild(modal);
    }
    delete window.currentExportData;
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 5px;
        color: white;
        font-weight: bold;
        z-index: 1002;
        animation: slideIn 0.3s ease-out;
    `;
    
    switch(type) {
        case 'success':
            notification.style.background = '#28a745';
            break;
        case 'error':
            notification.style.background = '#dc3545';
            break;
        default:
            notification.style.background = '#007bff';
    }
    
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Add animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    `;
    document.head.appendChild(style);
    
    // Remove after 3 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            document.body.removeChild(notification);
        }
        if (style.parentNode) {
            document.head.removeChild(style);
        }
    }, 3000);
}
