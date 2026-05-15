// ── DATA ──────────────────────────────────────────────────────────
const ALERTS = [
  {
    id: 1, severity: 'critical', title: 'High Latency — Cairo Cell-07',
    location: 'Cairo, Zone B', root_cause: 'Congestion',
    cause_explanation: 'PRB utilization exceeded 95% threshold causing queuing delays and packet retransmissions across the eMBB slice.',
    priority: 'critical', eta: '1–2 hours',
    suggested_solution: [
      'Offload traffic to adjacent Cell-09',
      'Enable load balancing on RNC',
      'Increase QoS priority for URLLC slice',
      'Schedule PRB expansion during maintenance window',
    ],
    affected_standards: ['TS 28.552 §5.1', 'TS 28.532 §7.3'],
    escalation_needed: true,
    additional_notes: 'SLA breach imminent. 3 enterprise clients affected.',
    ts: Date.now() - 420000, score: 0.91,
    symptoms: ['latency > 150ms', 'PRB > 95%', 'packet retransmission spike'],
    notified: ['engineer', 'call_center', 'client'],
  },
  {
    id: 2, severity: 'high', title: 'SLA Violation — Alexandria Macro-03',
    location: 'Alexandria, North', root_cause: 'SLA Breach',
    cause_explanation: 'Downlink throughput dropped below SLA threshold due to interference from adjacent sector.',
    priority: 'high', eta: '2–4 hours',
    suggested_solution: [
      'Adjust antenna tilt on Macro-03',
      'Check interference matrix SON report',
      'Trigger handover optimization',
    ],
    affected_standards: ['TS 28.552 §6.2'],
    escalation_needed: false,
    additional_notes: 'Throughput at 210 Mbps vs 300 Mbps SLA target.',
    ts: Date.now() - 1800000, score: 0.74,
    symptoms: ['throughput < 300Mbps', 'SINR low', 'handover failure rate 8%'],
    notified: ['engineer', 'call_center', 'client'],
  },
  {
    id: 3, severity: 'high', title: 'Packet Loss Spike — Giza HQ',
    location: 'Giza, HQ Site', root_cause: 'Link Degradation',
    cause_explanation: 'Backhaul link experiencing high BER due to weather-related interference on microwave hop.',
    priority: 'high', eta: '3–6 hours',
    suggested_solution: [
      'Switch backhaul to fiber redundancy',
      'Monitor BER threshold',
      'Alert NOC for physical inspection',
    ],
    affected_standards: ['TS 32.111 §4'],
    escalation_needed: true,
    additional_notes: 'Packet loss at 4.2% — above 2% SLA.',
    ts: Date.now() - 3600000, score: 0.68,
    symptoms: ['packet_loss 4.2%', 'BER elevated', 'jitter > 20ms'],
    notified: ['engineer', 'call_center', 'client'],
  },
  {
    id: 4, severity: 'medium', title: 'Weak RF Signal — Heliopolis Micro-12',
    location: 'Heliopolis, Sector 3', root_cause: 'RF Degradation',
    cause_explanation: 'RSRP dropped below –100 dBm likely due to antenna obstruction or hardware fault.',
    priority: 'medium', eta: '4–8 hours',
    suggested_solution: [
      'Schedule site inspection',
      'Check antenna connections',
      'Verify power amplifier output',
    ],
    affected_standards: ['TS 28.552 §5.3'],
    escalation_needed: false,
    additional_notes: 'Coverage hole forming in 300m radius.',
    ts: Date.now() - 7200000, score: 0.52,
    symptoms: ['RSRP < –100dBm', 'coverage complaint calls up 20%'],
    notified: ['call_center'],
  },
];

const RAG_FILES = [
  { name: '28532-i80.docx',              type: 'DOCX', chunks: 312, size: '1.2 MB' },
  { name: 'TS28532_PerfMnS.yaml',         type: 'YAML', chunks: 87,  size: '340 KB' },
  { name: 'TS28532_HeartbeatNtf.yaml',    type: 'YAML', chunks: 34,  size: '120 KB' },
  { name: '32111-1-i00.doc',              type: 'DOC',  chunks: 428, size: '2.1 MB' },
  { name: 'TeleQnA.txt',                  type: 'TXT',  chunks: 502, size: '6.7 MB' },
  { name: '3GPP_vocabulary.docx',         type: 'DOCX', chunks: 91,  size: '450 KB' },
];

// ── REAL DATA STATE ─────────────────────────────────────────────────
let REAL_SUMMARY  = null;
let REAL_ANOMALIES = [];
let REAL_MODELS   = null;
let currentFilter = 'all';
let uploadQueue   = [];

// ── LOAD REAL DATA FROM API ──────────────────────────────────────────
async function loadRealData() {
  try {
    const [sumRes, anomRes, modRes] = await Promise.all([
      fetch(`${API_BASE}/data/summary`),
      fetch(`${API_BASE}/data/anomalies?limit=256`),
      fetch(`${API_BASE}/data/models`),
    ]);
    if (!sumRes.ok || !anomRes.ok || !modRes.ok) return;

    REAL_SUMMARY   = await sumRes.json();
    const anomData = await anomRes.json();
    REAL_ANOMALIES = anomData.records || [];
    REAL_MODELS    = await modRes.json();

    _applyRealDataToDashboard();
    _applyRealDataToAlerts();
    _applyRealDataToModel();
  } catch (e) {
    console.warn('Real data API not reachable — using demo data', e);
  }
}

function _applyRealDataToDashboard() {
  if (!REAL_SUMMARY) return;
  const s = REAL_SUMMARY;

  _setText('val-throughput', `${s.dl_throughput_stats.mean.toFixed(1)}<span class="unit">Mbps</span>`);
  _setText('val-latency',    `${s.rsrp_stats.mean.toFixed(1)}<span class="unit">dBm</span>`);
  _setText('val-loss',       `${s.anomaly_rate.toFixed(2)}<span class="unit">%</span>`);
  _setText('val-alerts',     `<span class="glow">${s.anomaly_count}</span>`);

  _setText('delta-throughput', `max ${s.dl_throughput_stats.max} Mbps`);
  _setText('delta-latency',    `min ${s.rsrp_stats.min} / max ${s.rsrp_stats.max} dBm`);
  _setText('delta-loss',       `${s.anomaly_count} of ${s.total_measurements} measurements`);

  _updateGauge('gauge-rsrp', s.rsrp_stats.mean, -130, -60, 'var(--green)');
  _updateGauge('gauge-rsrq', s.rsrq_stats.mean, -25, -5,   'var(--yellow)');
  _updateGauge('gauge-sinr', s.sinr_stats.mean, -15, 30,   'var(--orange)');

  const total = s.anomaly_count || 1;
  _setWidth('bar-critical', (s.severity_distribution.critical / total * 100).toFixed(0));
  _setWidth('bar-high',     (s.severity_distribution.high     / total * 100).toFixed(0));
  _setWidth('bar-medium',   (s.severity_distribution.medium   / total * 100).toFixed(0));
  _setText('lbl-critical',  `${s.severity_distribution.critical}`);
  _setText('lbl-high',      `${s.severity_distribution.high}`);
  _setText('lbl-medium',    `${s.severity_distribution.medium}`);

  drawRealChart();
  drawAnomalyTypesChart();
  drawAreaChart();
}

function _applyRealDataToAlerts() {
  // Map real anomalies to ALERTS array format
  ALERTS.length = 0;
  REAL_ANOMALIES.slice(0, 50).forEach((r, i) => {
    ALERTS.push({
      id:               r.measurement_id,
      severity:         r.severity === 'low' ? 'medium' : r.severity,
      title:            `${r.anomaly_types[0] || 'ML Anomaly'} — ${r.area_name}`,
      location:         `${r.area_name}, ${r.district}`,
      root_cause:       r.root_causes[0] || r.anomaly_types[0] || 'Unknown',
      cause_explanation: r.root_causes.join(' | ') || 'ML-detected anomaly',
      priority:         r.severity,
      eta:              r.severity === 'critical' ? '1–2 hours' : r.severity === 'high' ? '2–4 hours' : '4–8 hours',
      suggested_solution: r.root_causes.length ? r.root_causes : ['Investigate signal metrics', 'Check cell hardware'],
      affected_standards: ['TS 28.552', 'TS 32.111'],
      escalation_needed:  r.severity === 'critical',
      additional_notes:   `RSRP: ${r.rsrp_dbm} dBm | RSRQ: ${r.rsrq_db} dB | SINR: ${r.sinr_db} dB`,
      ts:               new Date(r.time).getTime(),
      score:            r.ml_anomaly_score,
      symptoms:         r.anomaly_types,
      notified:         r.severity === 'critical' ? ['engineer','call_center','client']
                      : r.severity === 'high'     ? ['engineer','call_center']
                      :                             ['call_center'],
    });
  });

  // Re-render both alert lists
  renderAlerts(document.getElementById('dashboard-alerts'), ALERTS.slice(0, 3));
  renderAlerts(document.getElementById('alerts-list'),      ALERTS);
  document.getElementById('alert-badge-count').textContent = REAL_SUMMARY?.anomaly_count || ALERTS.length;
}

function _applyRealDataToModel() {
  if (!REAL_MODELS) return;
  const m = REAL_MODELS.metrics;
  const tbody = document.getElementById('model-metrics-table');
  if (!tbody) return;

  tbody.innerHTML = Object.entries(m).map(([name, v]) => `
    <tr>
      <td>${name}</td>
      <td><span class="badge ${v.f1_score >= 0.8 ? 'ok' : v.f1_score >= 0.6 ? 'medium' : 'high'}">${(v.f1_score * 100).toFixed(1)}%</span></td>
      <td>${(v.precision * 100).toFixed(1)}%</td>
      <td>${(v.recall * 100).toFixed(1)}%</td>
      <td>${(v.accuracy * 100).toFixed(1)}%</td>
      <td>${name === REAL_MODELS.best_model ? '⭐' : ''}</td>
    </tr>`).join('');

  drawFeatureImportanceChart();
}

// ── HELPERS ──────────────────────────────────────────────────────────
function _setText(id, html) { const el = document.getElementById(id); if (el) el.innerHTML = html; }
function _setWidth(id, pct) { const el = document.getElementById(id); if (el) el.style.width = pct + '%'; }

function _updateGauge(id, val, min, max, color) {
  const svg = document.getElementById(id);
  if (!svg) return;
  const pct = Math.max(0, Math.min(1, (val - min) / (max - min)));
  const C = 188.4;
  const offset = C - pct * C;
  const display = val.toFixed(1);
  svg.innerHTML = `
    <circle cx="36" cy="36" r="30" fill="none" stroke="var(--bg-3)" stroke-width="6"/>
    <circle cx="36" cy="36" r="30" fill="none" stroke="${color}" stroke-width="6"
      stroke-dasharray="${C}" stroke-dashoffset="${offset}" stroke-linecap="round" transform="rotate(-90 36 36)"/>
    <text x="36" y="40" text-anchor="middle" fill="var(--text-0)" font-size="10" font-family="IBM Plex Mono" font-weight="500">${display}</text>`;
}

// ── REAL CHARTS ──────────────────────────────────────────────────────
// live ticker — pushes a new point every second
let _chartBuffer = [];
let _chartTicker = null;
let _currentChartRange = '1H';

function drawRealChart(range = '1H') {
  _currentChartRange = range;
  const svg = document.getElementById('main-chart');
  if (!svg) return;

  if (REAL_ANOMALIES.length > 0 && _chartBuffer.length === 0) {
    const sorted = [...REAL_ANOMALIES].sort((a, b) => new Date(a.time) - new Date(b.time));
    _chartBuffer = sorted.map(r => r.ml_anomaly_score * 100);
  }

  const take = range === '1H' ? 60 : range === '6H' ? 120 : _chartBuffer.length || 60;
  const pts  = (_chartBuffer.length ? _chartBuffer : Array.from({length: 60}, () => Math.random() * 20)).slice(-take);
  _renderChart(svg, pts);
}

function _renderChart(svg, pts) {
  const W = 600, H = 200;
  const PAD = { top: 10, right: 10, bottom: 32, left: 48 };
  const cW = W - PAD.left - PAD.right;
  const cH = H - PAD.top - PAD.bottom;
  const xS = i => PAD.left + (i / (pts.length - 1 || 1)) * cW;
  const yS = v => PAD.top  + cH - (v / 100) * cH;

  const coords = pts.map((v, i) => [xS(i), yS(v)]);
  const line   = coords.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ');
  const area   = line + ` L${xS(pts.length-1)},${PAD.top+cH} L${PAD.left},${PAD.top+cH} Z`;

  let yLines = '', yLabels = '';
  [0, 25, 50, 75, 100].forEach(v => {
    const y = yS(v);
    yLines  += `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+cW}" y2="${y}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 4"/>`;
    yLabels += `<text x="${PAD.left-6}" y="${y+4}" text-anchor="end" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">${v}</text>`;
  });

  const step = Math.max(1, Math.floor(pts.length / 6));
  let xLabels = '';
  for (let i = 0; i < pts.length; i += step)
    xLabels += `<text x="${xS(i)}" y="${H-8}" text-anchor="middle" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">${i}</text>`;
  xLabels += `<text x="${xS(pts.length-1)}" y="${H-8}" text-anchor="middle" fill="var(--orange)" font-size="9" font-family="IBM Plex Mono">now</text>`;

  let zones = '', inZone = false, zoneStart = 0;
  pts.forEach((v, i) => {
    if (v > 50 && !inZone) { inZone = true; zoneStart = i; }
    else if (v <= 50 && inZone) {
      zones += `<rect x="${xS(zoneStart)}" y="${PAD.top}" width="${xS(i)-xS(zoneStart)}" height="${cH}" fill="rgba(232,69,10,0.08)"/>`;
      inZone = false;
    }
  });

  svg.innerHTML = `
    <defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--orange)" stop-opacity=".2"/>
      <stop offset="100%" stop-color="var(--orange)" stop-opacity="0"/>
    </linearGradient></defs>
    ${yLines}${zones}
    <path d="${area}" fill="url(#ag)"/>
    <path d="${line}" fill="none" stroke="var(--orange)" stroke-width="1.8" stroke-linejoin="round"/>
    <line x1="${PAD.left}" y1="${PAD.top}" x2="${PAD.left}" y2="${PAD.top+cH}" stroke="var(--border-lit)" stroke-width="1"/>
    <line x1="${PAD.left}" y1="${PAD.top+cH}" x2="${PAD.left+cW}" y2="${PAD.top+cH}" stroke="var(--border-lit)" stroke-width="1"/>
    ${yLabels}${xLabels}
    <text x="${PAD.left+cW/2}" y="${PAD.top+8}" text-anchor="middle" fill="var(--text-2)" font-size="8" font-family="IBM Plex Mono">Anomaly Score %</text>`;
}

function _startChartTicker() {
  if (_chartTicker) clearInterval(_chartTicker);
  _chartTicker = setInterval(() => {
    const svg = document.getElementById('main-chart');
    if (!svg) return;
    const last = _chartBuffer.length ? _chartBuffer[_chartBuffer.length - 1] : 10;
    const next = Math.max(0, Math.min(100, last + (Math.random() - 0.48) * 5));
    _chartBuffer.push(next);
    if (_chartBuffer.length > 500) _chartBuffer.shift();
    const take = _currentChartRange === '1H' ? 60 : _currentChartRange === '6H' ? 120 : _chartBuffer.length;
    _renderChart(svg, _chartBuffer.slice(-take));
  }, 1000);
}

function setChartRange(range, btn) {
  _currentChartRange = range;
  document.querySelectorAll('.chart-time-btn').forEach(b => { b.style.color = ''; b.style.borderColor = ''; });
  btn.style.color = 'var(--orange)';
  btn.style.borderColor = 'var(--orange)';
  drawRealChart(range);
}

  const W = 600, H = 200;
  const PAD = { top: 10, right: 10, bottom: 32, left: 44 };
  const cW = W - PAD.left - PAD.right;
  const cH = H - PAD.top - PAD.bottom;
  const minV = 0, maxV = 100;
  const xS = i  => PAD.left + (i / (pts.length - 1 || 1)) * cW;
  const yS = v  => PAD.top  + cH - ((v - minV) / (maxV - minV)) * cH;

  const coords = pts.map((v,i) => [xS(i), yS(v)]);
  const line   = coords.map((p,i) => (i===0?`M${p[0]},${p[1]}`:`L${p[0]},${p[1]}`)).join(' ');
  const area   = line + ` L${xS(pts.length-1)},${PAD.top+cH} L${PAD.left},${PAD.top+cH} Z`;

  // Y ticks
  let yLines='', yLabels='';
  [0,25,50,75,100].forEach(v => {
    const y = yS(v);
    yLines  += `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+cW}" y2="${y}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 4"/>`;
    yLabels += `<text x="${PAD.left-6}" y="${y+4}" text-anchor="end" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">${v}</text>`;
  });

  // X ticks — every 10 points
  let xLabels = '';
  const step = Math.max(1, Math.floor(pts.length / 6));
  for (let i=0; i<pts.length; i+=step) {
    xLabels += `<text x="${xS(i)}" y="${H-8}" text-anchor="middle" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">${i}</text>`;
  }
  xLabels += `<text x="${xS(pts.length-1)}" y="${H-8}" text-anchor="middle" fill="var(--orange)" font-size="9" font-family="IBM Plex Mono">latest</text>`;

  // Anomaly zone — scores > 50
  let zones = '';
  let inZone = false, zoneStart = 0;
  pts.forEach((v,i) => {
    if (v > 50 && !inZone) { inZone=true; zoneStart=i; }
    else if (v <= 50 && inZone) {
      zones += `<rect x="${xS(zoneStart)}" y="${PAD.top}" width="${xS(i)-xS(zoneStart)}" height="${cH}" fill="rgba(232,69,10,0.08)"/>`;
      inZone=false;
    }
  });

  svg.innerHTML = `
    <defs>
      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--orange)" stop-opacity=".2"/>
        <stop offset="100%" stop-color="var(--orange)" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${yLines}${zones}
    <path d="${area}" fill="url(#areaGrad)"/>
    <path d="${line}" fill="none" stroke="var(--orange)" stroke-width="1.8" stroke-linejoin="round"/>
    <line x1="${PAD.left}" y1="${PAD.top}" x2="${PAD.left}" y2="${PAD.top+cH}" stroke="var(--border-lit)" stroke-width="1"/>
    <line x1="${PAD.left}" y1="${PAD.top+cH}" x2="${PAD.left+cW}" y2="${PAD.top+cH}" stroke="var(--border-lit)" stroke-width="1"/>
    ${yLabels}${xLabels}
    <text x="${PAD.left+cW/2}" y="${PAD.top+8}" text-anchor="middle" fill="var(--text-2)" font-size="8" font-family="IBM Plex Mono">Anomaly Score %</text>`;
}

function drawAnomalyTypesChart() {
  const svg = document.getElementById('anomaly-types-chart');
  if (!svg || !REAL_SUMMARY) return;
  const dist = REAL_SUMMARY.anomaly_types_distribution;
  const entries = Object.entries(dist).slice(0, 6).sort((a,b) => b[1]-a[1]);
  const maxVal  = entries[0]?.[1] || 1;
  const W = 500, barH = 22, gap = 8, labelW = 220, padding = 10;
  const totalH  = entries.length * (barH + gap) + 2*padding;
  const colors  = ['var(--orange)','var(--red)','var(--yellow)','var(--blue)','var(--green)','var(--orange-hi)'];

  const bars = entries.map(([name, val], i) => {
    const barW = ((val / maxVal) * (W - labelW - 50)).toFixed(0);
    const y = padding + i * (barH + gap);
    const shortName = name.length > 28 ? name.slice(0, 28) + '…' : name;
    return `
      <text x="${labelW-6}" y="${y + barH/2 + 4}" text-anchor="end" fill="var(--text-1)" font-size="9" font-family="IBM Plex Mono">${shortName}</text>
      <rect x="${labelW}" y="${y}" width="${barW}" height="${barH}" rx="3" fill="${colors[i]}" opacity=".8"/>
      <text x="${labelW + parseFloat(barW) + 6}" y="${y + barH/2 + 4}" fill="var(--text-0)" font-size="9" font-family="IBM Plex Mono" font-weight="500">${val}</text>`;
  }).join('');

  svg.setAttribute('viewBox', `0 0 ${W} ${totalH}`);
  svg.setAttribute('height', totalH);
  svg.innerHTML = bars;
}

function drawAreaChart() {
  const svg = document.getElementById('area-chart');
  if (!svg || !REAL_SUMMARY) return;
  const areas = REAL_SUMMARY.top_anomaly_areas;
  const entries = Object.entries(areas);
  const total   = entries.reduce((s,[,v]) => s+v, 0);
  const colors  = ['var(--orange)','var(--red)','var(--yellow)','var(--blue)'];
  const R = 60, cx = 80, cy = 70;
  let startAngle = -Math.PI/2;
  let slices = '', legend = '';

  entries.forEach(([name, val], i) => {
    const angle   = (val / total) * 2 * Math.PI;
    const endAngle = startAngle + angle;
    const x1 = cx + R * Math.cos(startAngle);
    const y1 = cy + R * Math.sin(startAngle);
    const x2 = cx + R * Math.cos(endAngle);
    const y2 = cy + R * Math.sin(endAngle);
    const large = angle > Math.PI ? 1 : 0;
    slices += `<path d="M${cx},${cy} L${x1.toFixed(1)},${y1.toFixed(1)} A${R},${R} 0 ${large},1 ${x2.toFixed(1)},${y2.toFixed(1)} Z" fill="${colors[i]}" opacity=".85"/>`;
    legend += `
      <rect x="165" y="${10 + i*22}" width="10" height="10" rx="2" fill="${colors[i]}"/>
      <text x="180" y="${20 + i*22}" fill="var(--text-1)" font-size="9" font-family="IBM Plex Mono">${name} (${val})</text>`;
    startAngle = endAngle;
  });

  svg.innerHTML = slices + legend + `<text x="${cx}" y="${cy+4}" text-anchor="middle" fill="var(--text-0)" font-size="9" font-family="IBM Plex Mono" font-weight="600">${total} total</text>`;
}

function drawFeatureImportanceChart() {
  const svg = document.getElementById('feature-importance-chart');
  if (!svg || !REAL_MODELS) return;
  const features = REAL_MODELS.feature_importance_xgb.slice(0, 8);
  const maxImp   = features[0]?.importance || 1;
  const W = 440, barH = 20, gap = 7, labelW = 160, padding = 8;
  const totalH = features.length * (barH + gap) + 2*padding;

  const bars = features.map((f, i) => {
    const barW = ((f.importance / maxImp) * (W - labelW - 60)).toFixed(0);
    const y = padding + i * (barH + gap);
    return `
      <text x="${labelW-6}" y="${y+barH/2+4}" text-anchor="end" fill="var(--text-1)" font-size="9" font-family="IBM Plex Mono">${f.feature}</text>
      <rect x="${labelW}" y="${y}" width="${barW}" height="${barH}" rx="3" fill="var(--orange)" opacity="${0.5 + f.importance/maxImp*0.5}"/>
      <text x="${labelW+parseFloat(barW)+6}" y="${y+barH/2+4}" fill="var(--text-0)" font-size="9" font-family="IBM Plex Mono">${(f.importance*100).toFixed(1)}%</text>`;
  }).join('');

  svg.setAttribute('viewBox', `0 0 ${W} ${totalH}`);
  svg.setAttribute('height', totalH);
  svg.innerHTML = bars;
}

// ── CLOCK ──────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date().toTimeString().slice(0, 8);
  const clock = document.getElementById('clock');
  const mobileClock = document.getElementById('mobile-clock');
  if (clock) clock.textContent = now;
  if (mobileClock) mobileClock.textContent = now;
}
setInterval(updateClock, 1000);
updateClock();

// ── NAVIGATION ─────────────────────────────────────────────────────
function showPage(name, btn) {
  document.querySelectorAll('.page.main').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  if (btn) btn.classList.add('active');
  closeMobileNav();
}

// ── HELPERS ─────────────────────────────────────────────────────────
function timeAgo(ts) {
  const m = Math.floor((Date.now() - ts) / 60000);
  if (m < 60)  return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24)  return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}

function severityIcon(s) {
  const icons = {
    critical: `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    high:     `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    medium:   `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
    low:      `<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  };
  return icons[s] || icons.low;
}

// ── RENDER ALERTS ───────────────────────────────────────────────────
function renderAlerts(container, alerts) {
  if (!alerts.length) {
    container.innerHTML = `<div class="empty-state"><p>No alerts found</p></div>`;
    return;
  }
  container.innerHTML = alerts.map(a => `
    <div class="alert-item ${a.severity}" onclick="openPanel(${a.id})">
      <div class="alert-icon">${severityIcon(a.severity)}</div>
      <div class="alert-body">
        <div class="alert-title">${a.title}</div>
        <div class="alert-meta">
          <span>${a.location}</span>
          <span>${a.root_cause}</span>
          <span>${timeAgo(a.ts)}</span>
        </div>
      </div>
      <div class="alert-score">${Math.round(a.score * 100)}%</div>
    </div>
  `).join('');
}

function filterAlerts(f, btn) {
  currentFilter = f;
  document.querySelectorAll('#page-alerts .btn[onclick^="filterAlerts"]')
    .forEach(b => b.className = 'btn btn-ghost btn-sm');
  if (btn) btn.className = 'btn btn-primary btn-sm';
  const list = f === 'all' ? ALERTS : ALERTS.filter(a => a.severity === f);
  renderAlerts(document.getElementById('alerts-list'), list);
}

function searchAlerts(q) {
  const lq = q.toLowerCase();
  const base = currentFilter === 'all' ? ALERTS : ALERTS.filter(a => a.severity === currentFilter);
  renderAlerts(
    document.getElementById('alerts-list'),
    base.filter(a =>
      a.title.toLowerCase().includes(lq) ||
      a.location.toLowerCase().includes(lq) ||
      a.root_cause.toLowerCase().includes(lq)
    )
  );
}

// ── DETAIL PANEL ────────────────────────────────────────────────────
function openPanel(id) {
  const a = ALERTS.find(x => x.id === id);
  if (!a) return;

  document.getElementById('panel-title').textContent = a.title;
  document.getElementById('panel-body').innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
      <span class="badge ${a.severity}">${a.severity.toUpperCase()}</span>
      <span style="font-size:.75rem;color:var(--text-2);">${timeAgo(a.ts)}</span>
    </div>
    <div style="margin-bottom:14px;">
      <div style="font-size:.68rem;color:var(--text-2);text-transform:uppercase;letter-spacing:.09em;margin-bottom:6px;">Anomaly Score</div>
      <div style="display:flex;align-items:center;gap:10px;">
        <div class="score-meter" style="flex:1;"><div class="score-fill" style="width:${a.score*100}%"></div></div>
        <span style="font-family:var(--font-display);font-weight:700;">${Math.round(a.score*100)}%</span>
      </div>
    </div>
    <div class="detail-row"><div class="detail-key">Location</div><div class="detail-val">${a.location}</div></div>
    <div class="detail-row"><div class="detail-key">Root Cause</div><div class="detail-val">${a.root_cause}</div></div>
    <div class="detail-row">
      <div class="detail-key">Cause Explanation</div>
      <div class="detail-val" style="color:var(--text-1);font-size:.8rem;">${a.cause_explanation}</div>
    </div>
    <div class="detail-row">
      <div class="detail-key">Symptoms</div>
      <div class="detail-val"><div class="tag-list">${a.symptoms.map(s=>`<span class="tag">${s}</span>`).join('')}</div></div>
    </div>
    <div class="detail-row"><div class="detail-key">Estimated Resolution</div><div class="detail-val">${a.eta}</div></div>
    <div class="detail-row">
      <div class="detail-key">Escalation Needed</div>
      <div class="detail-val" style="color:${a.escalation_needed?'var(--red)':'var(--green)'}">
        ${a.escalation_needed ? '⚠ Yes — Escalate to NOC' : '✓ No'}
      </div>
    </div>
    <div class="detail-row">
      <div class="detail-key">Suggested Solution</div>
      <div class="detail-val">
        <div class="solution-steps">
          ${a.suggested_solution.map((s,i)=>`<div class="solution-step"><span class="step-num">${i+1}</span><span>${s}</span></div>`).join('')}
        </div>
      </div>
    </div>
    <div class="detail-row">
      <div class="detail-key">Affected Standards</div>
      <div class="detail-val"><div class="tag-list">${a.affected_standards.map(s=>`<span class="tag" style="color:var(--orange);border-color:var(--orange-lo)">${s}</span>`).join('')}</div></div>
    </div>
    <div class="detail-row">
      <div class="detail-key">Notified</div>
      <div class="detail-val"><div class="tag-list">${a.notified.map(r=>`<span class="tag" style="color:var(--green);border-color:var(--green-lo)">✓ ${r}</span>`).join('')}</div></div>
    </div>
    ${a.additional_notes ? `<div class="detail-row"><div class="detail-key">Notes</div><div class="detail-val" style="color:var(--text-2);font-size:.78rem;">${a.additional_notes}</div></div>` : ''}
    <div style="display:flex;gap:8px;margin-top:20px;">
      <button class="btn btn-primary" onclick="closePanel()">
        <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="width:13px;height:13px;"><path d="M22 2L11 13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        Resend Notifications
      </button>
      <button class="btn btn-ghost" onclick="closePanel()">Close</button>
    </div>
  `;
  document.getElementById('detail-panel').classList.add('open');
}

function closePanel() {
  document.getElementById('detail-panel').classList.remove('open');
}

// ── RAG FILES ───────────────────────────────────────────────────────
function renderRagFiles() {
  document.getElementById('rag-files-table').innerHTML = RAG_FILES.map(f => `
    <tr>
      <td>${f.name}</td>
      <td><span class="badge ok">${f.type}</span></td>
      <td>${f.chunks}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="deleteRagFile('${f.name}', this)">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
          Delete
        </button>
      </td>
    </tr>
  `).join('');
}

function deleteRagFile(name, btn) {
  const row = btn.closest('tr');
  row.style.opacity = '.3';
  row.style.transition = 'opacity .3s';
  setTimeout(() => {
    const idx = RAG_FILES.findIndex(f => f.name === name);
    if (idx > -1) RAG_FILES.splice(idx, 1);
    renderRagFiles();
  }, 400);
}

// ── FILE UPLOAD ─────────────────────────────────────────────────────
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.add('drag-over');
}
function handleDragLeave() {
  document.getElementById('upload-zone').classList.remove('drag-over');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag-over');
  handleFiles(e.dataTransfer.files);
}
function handleFiles(files) {
  Array.from(files).forEach(f => { uploadQueue.push(f); addFileToQueue(f); });
}
function addFileToQueue(file) {
  const el = document.createElement('div');
  el.className = 'file-item';
  el.id = 'file-' + file.name.replace(/\W/g, '_');
  el.innerHTML = `
    <div class="file-icon-wrap">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
    </div>
    <div class="file-info">
      <div class="file-name">${file.name}</div>
      <div class="file-size">${(file.size/1024).toFixed(0)} KB</div>
    </div>
    <span class="badge medium">Queued</span>
  `;
  document.getElementById('upload-queue').appendChild(el);
}
function clearQueue() {
  uploadQueue = [];
  document.getElementById('upload-queue').innerHTML = '';
  document.getElementById('ingest-progress').classList.remove('visible');
}

// ── SIMULATED INGESTION ─────────────────────────────────────────────
function startIngest() {
  if (!uploadQueue.length) { alert('Add files first'); return; }
  document.getElementById('ingest-progress').classList.add('visible');

  const steps = ['step-load', 'step-chunk', 'step-embed', 'step-store'];
  const bar = document.getElementById('ingest-bar');
  let i = 0;

  function nextStep() {
    if (i > 0) {
      const prev = document.getElementById(steps[i-1]);
      prev.classList.remove('active');
      prev.classList.add('done');
    }
    if (i >= steps.length) {
      bar.style.width = '100%';
      uploadQueue.forEach(f => {
        const el = document.getElementById('file-' + f.name.replace(/\W/g, '_'));
        if (el) { const b = el.querySelector('.badge'); b.className = 'badge ok'; b.textContent = 'Indexed'; }
        RAG_FILES.push({ name: f.name, type: f.name.split('.').pop().toUpperCase(), chunks: Math.floor(Math.random()*200+50), size: (f.size/1024).toFixed(0)+' KB' });
      });
      uploadQueue = [];
      renderRagFiles();
      return;
    }
    document.getElementById(steps[i]).classList.add('active');
    bar.style.width = ((i+1) / steps.length * 100) + '%';
    i++;
    setTimeout(nextStep, 1200 + Math.random()*600);
  }
  nextStep();
}

// ── CONFIG API ───────────────────────────────────────────────────────
// في Codespaces الـ URL بيكون مختلف — بنبني الـ API URL من الـ current host
const API_BASE = (() => {
  const h = window.location.hostname;
  // Codespaces
  if (h.includes('app.github.dev')) {
    return window.location.origin.replace('-3000.', '-8000.');
  }
  // Docker — nginx proxies /api/ to rag_api:8000
  return window.location.origin + '/api';
})();

async function loadConfig() {
  try {
    const res = await fetch(`${API_BASE}/config`);
    if (!res.ok) return;
    const cfg = await res.json();

    // emails
    _setField('engineer-email',   cfg.engineer_email);
    _setField('callcenter-email', cfg.callcenter_email);
    _setField('client-email',     cfg.client_email);
    _setDisplay('engineer-email-display',   cfg.engineer_email   || '(not set)');
    _setDisplay('callcenter-email-display', cfg.callcenter_email || '(not set)');
    _setDisplay('client-email-display',     cfg.client_email     || '(not set)');

    // smtp
    _setField('smtp-sender', cfg.smtp_sender);

    // footer status
    const modelEl = document.getElementById('footer-model');
    if (modelEl) modelEl.textContent = cfg.gemini_model || 'Unknown';

  } catch (_) {
    // API offline — keep placeholders
  }
}

async function saveConfig() {
  const payload = {
    engineer_email:   document.getElementById('engineer-email')?.value   || '',
    call_center_email: document.getElementById('callcenter-email')?.value || '',
    client_email:     document.getElementById('client-email')?.value     || '',
    smtp_sender:      document.getElementById('smtp-sender')?.value      || '',
  };
  try {
    await fetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const btn = document.getElementById('save-config-btn');
    if (btn) { const orig = btn.innerHTML; btn.textContent = '✓ Saved'; btn.style.background = 'var(--green)'; setTimeout(() => { btn.innerHTML = orig; btn.style.background = ''; }, 1800); }
  } catch (_) {
    alert('Could not reach API');
  }
}

function _setField(id, val) {
  const el = document.getElementById(id);
  if (el && val) el.value = val;
}
function _setDisplay(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function toggleRecipient(role, cb) {
  const el = document.getElementById(role + '-email-display');
  if (el) el.style.textDecoration = cb.checked ? 'none' : 'line-through';
}
function switchTemplate(name, btn) {
  document.querySelectorAll('.tmpl-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tmpl-content').forEach(c => c.style.display = 'none');
  btn.classList.add('active');
  document.getElementById('tmpl-' + name).style.display = 'block';
}
function saveTemplates() {
  const btn = event.currentTarget;
  const orig = btn.innerHTML;
  btn.innerHTML = '✓ Saved';
  btn.style.background = 'var(--green)';
  setTimeout(() => { btn.innerHTML = orig; btn.style.background = ''; }, 1800);
}
async function testSmtp() {
  const btn = event.currentTarget;
  const orig = btn.innerHTML;
  btn.textContent = 'Sending…';
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/test-email`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      btn.textContent = `✓ Sent to ${data.to}`;
      btn.style.color = 'var(--green)';
    } else {
      btn.textContent = `✗ ${data.detail}`;
      btn.style.color = 'var(--red)';
    }
  } catch (_) {
    btn.textContent = '✗ API unreachable';
    btn.style.color = 'var(--red)';
  }

  setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; btn.disabled = false; }, 3500);
}

// ── CHARTS ──────────────────────────────────────────────────────────
function generatePoints(n, min, max, noise) {
  let v = (min + max) / 2;
  return Array.from({ length: n }, () => {
    v += (Math.random() - 0.5) * noise;
    v = Math.max(min, Math.min(max, v));
    return v;
  });
}

function drawMainChart(noise = 80) {
  const svg = document.getElementById('main-chart');
  if (!svg) return;
  const W = 600, H = 200;
  const PAD = { top: 10, right: 10, bottom: 32, left: 44 };
  const cW = W - PAD.left - PAD.right;
  const cH = H - PAD.top - PAD.bottom;

  const pts = generatePoints(60, 400, 1000, noise);
  const minV = Math.floor(Math.min(...pts) / 100) * 100;
  const maxV = Math.ceil(Math.max(...pts)  / 100) * 100;

  const xScale = i  => PAD.left + (i / (pts.length - 1)) * cW;
  const yScale = v  => PAD.top  + cH - ((v - minV) / (maxV - minV)) * cH;

  const coords = pts.map((v, i) => [xScale(i), yScale(v)]);
  const line   = coords.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ');
  const area   = line + ` L${xScale(pts.length-1)},${PAD.top+cH} L${PAD.left},${PAD.top+cH} Z`;

  // Y axis labels & grid lines (5 ticks)
  const yTicks = 5;
  let yLines = '', yLabels = '';
  for (let t = 0; t <= yTicks; t++) {
    const val = minV + (t / yTicks) * (maxV - minV);
    const y   = yScale(val);
    yLines  += `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left + cW}" y2="${y}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 4"/>`;
    yLabels += `<text x="${PAD.left - 6}" y="${y + 4}" text-anchor="end" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">${Math.round(val)}</text>`;
  }

  // X axis labels (every 10 points = ~10 min)
  let xLabels = '';
  const xStep = 10;
  for (let i = 0; i < pts.length; i += xStep) {
    const x   = xScale(i);
    const min = (pts.length - 1 - i);
    xLabels += `<text x="${x}" y="${H - 8}" text-anchor="middle" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">-${min}m</text>`;
  }
  // "now" label
  xLabels += `<text x="${xScale(pts.length-1)}" y="${H - 8}" text-anchor="middle" fill="var(--orange)" font-size="9" font-family="IBM Plex Mono">now</text>`;

  // Anomaly highlight zone
  const zoneX = xScale(28);
  const zoneW = xScale(36) - xScale(28);

  svg.innerHTML = `
    <defs>
      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--orange)" stop-opacity=".22"/>
        <stop offset="100%" stop-color="var(--orange)" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${yLines}
    <rect x="${zoneX}" y="${PAD.top}" width="${zoneW}" height="${cH}" fill="rgba(232,69,10,0.07)" rx="2"/>
    <text x="${zoneX + zoneW/2}" y="${PAD.top + 12}" text-anchor="middle" fill="var(--orange)" font-size="8" font-family="IBM Plex Mono" opacity=".7">anomaly</text>
    <path d="${area}" fill="url(#areaGrad)"/>
    <path d="${line}" fill="none" stroke="var(--orange)" stroke-width="1.8" stroke-linejoin="round"/>
    <line x1="${PAD.left}" y1="${PAD.top}" x2="${PAD.left}" y2="${PAD.top+cH}" stroke="var(--border-lit)" stroke-width="1"/>
    <line x1="${PAD.left}" y1="${PAD.top+cH}" x2="${PAD.left+cW}" y2="${PAD.top+cH}" stroke="var(--border-lit)" stroke-width="1"/>
    ${yLabels}
    ${xLabels}
  `;
}

function drawSparkline(id, min, max, color) {
  const svg = document.getElementById(id);
  if (!svg) return;
  const pts = generatePoints(20, min, max, (max - min) / 4);
  const minV = Math.min(...pts), maxV = Math.max(...pts);
  const coords = pts.map((v, i) => [
    (i / (pts.length - 1)) * 80,
    40 - ((v - minV) / (maxV - minV + 1)) * 36 - 2,
  ]);
  const line = coords.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ');
  svg.innerHTML = `<path d="${line}" fill="none" stroke="${color || 'var(--orange)'}" stroke-width="1.5"/>`;
}

// ── LIVE UPDATE ──────────────────────────────────────────────────────
function liveUpdate() {
  const tp   = Math.round(780 + Math.random() * 120);
  const lat  = (10 + Math.random() * 6).toFixed(0);
  const loss = (0.2 + Math.random() * 0.3).toFixed(2);
  document.getElementById('val-throughput').innerHTML = `${tp}<span class="unit">Mbps</span>`;
  document.getElementById('val-latency').innerHTML    = `${lat}<span class="unit">ms</span>`;
  document.getElementById('val-loss').innerHTML       = `${loss}<span class="unit">%</span>`;
  drawMainChart();
  drawSparkline('spark-throughput', 700, 1000, 'var(--green)');
}

// ── THEME ─────────────────────────────────────────────────────────────
function toggleTheme() {
  document.body.classList.toggle('light');
  localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
}

function toggleMobileNav(btn) {
  const topbar = document.querySelector('.topbar');
  if (!topbar) return;
  const isOpen = topbar.classList.toggle('menu-open');
  if (btn) btn.setAttribute('aria-expanded', String(isOpen));
}

function closeMobileNav() {
  const topbar = document.querySelector('.topbar');
  const toggle = document.querySelector('.mobile-nav-toggle');
  if (!topbar) return;
  topbar.classList.remove('menu-open');
  if (toggle) toggle.setAttribute('aria-expanded', 'false');
}

// ── CHART TIME BUTTONS ─────────────────────────────────────────────────
function setChartRange(range, btn) {
  document.querySelectorAll('.chart-time-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // redraw with different noise to simulate different range
  const noise = range === '1H' ? 60 : range === '6H' ? 100 : 140;
  drawMainChart(noise);
}

// ── CHAT ─────────────────────────────────────────────────────────────
async function sendChat() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;

  input.value = '';
  document.getElementById('chat-suggestions').style.display = 'none';

  _appendMsg(q, 'user');
  const loadingId = _appendMsg('Thinking...', 'assistant loading');

  try {
    const res = await fetch(`${API_BASE}/query/general`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      _updateMsg(loadingId, `Error: ${err.detail || res.status}`);
      return;
    }
    const data = await res.json();
    _updateMsg(loadingId, data.answer || 'No response from RAG.');
  } catch (_) {
    _updateMsg(loadingId, 'Cannot reach the RAG API. Make sure the backend is running.');
  }
}

function sendSuggestion(btn) {
  document.getElementById('chat-input').value = btn.textContent;
  btn.closest('.suggestion-chip')?.remove();
  btn.remove();
  sendChat();
}

function _appendMsg(text, classes) {
  const id = 'msg-' + Date.now();
  const msgs = document.getElementById('chat-messages');
  const isUser = classes.includes('user');
  msgs.innerHTML += `
    <div class="chat-msg ${classes}" id="${id}">
      <div class="chat-bubble">${isUser ? text : text}</div>
    </div>`;
  msgs.scrollTop = msgs.scrollHeight;
  return id;
}

function _updateMsg(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'chat-msg assistant';
  el.querySelector('.chat-bubble').textContent = text;
}

// ── ANALYZE (ML → RAG) ───────────────────────────────────────────────
// ── LIVE DEMO ────────────────────────────────────────────────────────
const DEMO_SCENARIOS = {
  critical: {
    severity: 'critical', ml_anomaly_score: 0.91,
    location: 'Westbahnhof, Vienna', cell_id: '107011',
    anomaly_types: ['High path loss (123 dB)', 'RSRP deviation detected (-113.4 dBm)'],
    root_causes: ['Extreme signal weakness - possible coverage hole or hardware fault', 'Excessive propagation loss - indoor or behind obstacle'],
    rsrp_dbm: -113.4, rsrq_db: -24.3, sinr_db: -12.7, dl_throughput_mbps: 0.0,
  },
  high: {
    severity: 'high', ml_anomaly_score: 0.74,
    location: 'Mariahilfer Strasse, Vienna', cell_id: '129795',
    anomaly_types: ['RSRQ deviation detected (-18.9 dB)', 'Composite signal quality degradation'],
    root_causes: ['Severe interference - PCI conflict or external RF source', 'Overall signal quality index below acceptable'],
    rsrp_dbm: -102.6, rsrq_db: -18.9, sinr_db: -4.3, dl_throughput_mbps: 7.4,
  },
  medium: {
    severity: 'medium', ml_anomaly_score: 0.52,
    location: 'Karlsplatz, Vienna', cell_id: '163341',
    anomaly_types: ['ML-detected statistical anomaly', 'Multi-metric degradation (2 KPIs below normal)'],
    root_causes: ['Pattern deviation detected by AI - subtle metric combination unusual'],
    rsrp_dbm: -97.4, rsrq_db: -14.4, sinr_db: 0.4, dl_throughput_mbps: 23.5,
  },
};

let _demoRecord = null;

function runDemo(type) {
  if (type === 'replay') {
    const real = REAL_ANOMALIES.find(r => r.severity === 'critical') || REAL_ANOMALIES[0];
    if (!real) { document.getElementById('demo-status').textContent = 'No real data loaded yet'; return; }
    _demoRecord = [{
      severity:         real.severity,
      ml_anomaly_score: real.ml_anomaly_score,
      location:         `${real.area_name}, ${real.district}`,
      cell_id:          String(real.cell_id),
      anomaly_types:    real.anomaly_types,
      root_causes:      real.root_causes,
      rsrp_dbm:         real.rsrp_dbm,
      rsrq_db:          real.rsrq_db,
      sinr_db:          real.sinr_db,
      dl_throughput_mbps: real.dl_throughput_mbps,
    }];
  } else {
    _demoRecord = [DEMO_SCENARIOS[type]];
  }

  document.getElementById('demo-preview').textContent = JSON.stringify(_demoRecord[0], null, 2);
  document.getElementById('demo-run-btn').disabled = false;
  document.getElementById('demo-status').textContent = 'Ready — click Run & Analyze';
  document.getElementById('demo-result').style.display = 'none';
}

async function submitDemo() {
  if (!_demoRecord) return;
  const btn = document.getElementById('demo-run-btn');
  const status = document.getElementById('demo-status');

  btn.disabled = true;
  btn.innerHTML = '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" width="14" height="14"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> Analyzing…';
  status.textContent = 'Sending to RAG pipeline…';
  status.style.color = 'var(--orange)';

  try {
    const res  = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_demoRecord),
    });
    const data = await res.json();

    const rag  = data.rag_result || {};
    const notif = data.notification || {};

    document.getElementById('demo-cause').textContent =
      rag.cause_explanation || 'No explanation returned (RAG knowledge base may be empty)';
    document.getElementById('demo-eta').textContent =
      rag.estimated_resolution_time ? `ETA: ${rag.estimated_resolution_time}` : '';

    const notified = notif.recipients_notified || [];
    document.getElementById('demo-notified').innerHTML = notified.length
      ? notified.map(r => `<span class="badge ok" style="margin-right:4px;">✓ ${r}</span>`).join('')
      : '<span style="color:var(--text-2);">No emails configured — check Settings</span>';

    const errors = notif.errors || [];
    document.getElementById('demo-errors').textContent = errors.join(' | ');

    const steps = rag.suggested_solution || [];
    document.getElementById('demo-steps').innerHTML = steps.length
      ? steps.map((s, i) => `<div style="margin-bottom:4px;"><span style="color:var(--orange);font-weight:600;">${i+1}.</span> ${s}</div>`).join('')
      : 'No steps returned.';

    document.getElementById('demo-result').style.display = 'block';
    status.textContent = `Done — ${data.processed} record analyzed, ${notified.length} notified`;
    status.style.color = 'var(--green)';

  } catch (e) {
    status.textContent = `Error: ${e.message}`;
    status.style.color = 'var(--red)';
  }

  btn.disabled = false;
  btn.innerHTML = '<svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" width="14" height="14"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run & Analyze';
}
  const raw = document.getElementById('ml-output-input').value.trim();
  const resultEl  = document.getElementById('analyze-result');
  const resultJSON = document.getElementById('analyze-result-json');

  let records;
  try { records = JSON.parse(raw); }
  catch (_) { alert('Invalid JSON — paste a valid array'); return; }

  resultEl.style.display = 'block';
  resultJSON.textContent = 'Sending to RAG pipeline…';

  try {
    const res  = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(records),
    });
    const data = await res.json();
    resultJSON.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    resultJSON.textContent = 'Error: ' + e.message;
  }
}
document.addEventListener('DOMContentLoaded', () => {
  if (localStorage.getItem('theme') === 'light') document.body.classList.add('light');

  drawRealChart();
  drawSparkline('spark-throughput', 700, 1000, 'var(--green)');

  renderAlerts(document.getElementById('dashboard-alerts'), ALERTS.slice(0, 3));
  renderAlerts(document.getElementById('alerts-list'), ALERTS);
  renderRagFiles();

  loadRealData();
  loadConfig();
  _startChartTicker();
});
