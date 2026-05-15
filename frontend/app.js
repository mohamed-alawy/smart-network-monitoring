// app.js — NetPulse Network Monitoring Dashboard

const ALERTS = [
  { id:1, severity:'critical', title:'High Path Loss — Westbahnhof', location:'Westbahnhof, Vienna', root_cause:'Coverage Hole', cause_explanation:'Path loss 123dB, RSRP -113.4dBm. Severe propagation loss.', priority:'critical', eta:'1-2 hours', suggested_solution:['Dispatch field engineer','Check antenna hardware','Verify backhaul link'], affected_standards:['TS 28.552','TS 32.111'], escalation_needed:true, additional_notes:'0 Mbps DL throughput.', ts:Date.now()-420000, score:0.91, symptoms:['Path loss 123dB','RSRP -113.4dBm','DL 0 Mbps'], notified:['engineer','call_center','client'] },
  { id:2, severity:'high', title:'RF Interference — Mariahilfer Strasse', location:'Mariahilfer Strasse, Vienna', root_cause:'PCI Conflict', cause_explanation:'RSRQ -18.9dB and SINR -4.3dB indicate severe interference.', priority:'high', eta:'2-4 hours', suggested_solution:['Run interference scan','Check neighboring cells','Adjust antenna tilt'], affected_standards:['TS 28.552'], escalation_needed:false, additional_notes:'7.4 Mbps vs expected 50+ Mbps.', ts:Date.now()-1800000, score:0.74, symptoms:['RSRQ -18.9dB','SINR -4.3dB'], notified:['engineer','call_center','client'] },
  { id:3, severity:'medium', title:'ML Anomaly — Karlsplatz', location:'Karlsplatz, Vienna', root_cause:'Pattern Deviation', cause_explanation:'ML detected subtle metric combination outside normal distribution.', priority:'medium', eta:'4-8 hours', suggested_solution:['Monitor for 1 hour','Check SON reports'], affected_standards:['TS 28.552'], escalation_needed:false, additional_notes:'Score 0.52 borderline.', ts:Date.now()-3600000, score:0.52, symptoms:['2 KPIs below normal'], notified:['call_center'] },
];

const RAG_FILES = [
  { name:'28532-i80.docx', type:'DOCX', chunks:312, size:'1.2 MB' },
  { name:'TS28532_PerfMnS.yaml', type:'YAML', chunks:87, size:'340 KB' },
  { name:'TS28532_HeartbeatNtf.yaml', type:'YAML', chunks:34, size:'120 KB' },
  { name:'32111-1-i00.doc', type:'DOC', chunks:428, size:'2.1 MB' },
  { name:'TeleQnA.txt', type:'TXT', chunks:502, size:'6.7 MB' },
  { name:'3GPP_vocabulary.docx', type:'DOCX', chunks:91, size:'450 KB' },
];

let REAL_SUMMARY = null, REAL_ANOMALIES = [], REAL_MODELS = null;
let currentFilter = 'all', uploadQueue = [];

const API_BASE = (() => {
  const h = window.location.hostname;
  // Codespaces — replace port 3000 with 8000 in the hostname
  if (h.includes('app.github.dev')) {
    return 'https://' + h.replace('-3000.', '-8000.');
  }
  // Local Docker — nginx proxies /api/ to rag_api:8000
  return '/api';
})();

// ── REAL DATA ──────────────────────────────────────────────────────
async function loadRealData() {
  try {
    const [sR, aR, mR] = await Promise.all([
      fetch(API_BASE + '/data/summary'),
      fetch(API_BASE + '/data/anomalies?limit=256'),
      fetch(API_BASE + '/data/models'),
    ]);
    if (!sR.ok) return;
    REAL_SUMMARY   = await sR.json();
    REAL_ANOMALIES = (await aR.json()).records || [];
    REAL_MODELS    = await mR.json();
    _applyDashboard();
    _applyAlerts();
    _applyModel();
  } catch(e) { console.warn('API not reachable', e); }
}

function _applyDashboard() {
  const s = REAL_SUMMARY; if (!s) return;
  _html('val-throughput', s.dl_throughput_stats.mean.toFixed(1) + '<span class="unit">Mbps</span>');
  _html('val-latency',    s.rsrp_stats.mean.toFixed(1) + '<span class="unit">dBm</span>');
  _html('val-loss',       s.anomaly_rate.toFixed(2) + '<span class="unit">%</span>');
  _html('val-alerts',     '<span class="glow">' + s.anomaly_count + '</span>');
  _txt('delta-throughput', 'max ' + s.dl_throughput_stats.max + ' Mbps');
  _txt('delta-latency',    'min ' + s.rsrp_stats.min + ' / max ' + s.rsrp_stats.max + ' dBm');
  _txt('delta-loss',       s.anomaly_count + ' of ' + s.total_measurements + ' measurements');
  _gauge('gauge-rsrp', s.rsrp_stats.mean, -130, -60, 'var(--green)');
  _gauge('gauge-rsrq', s.rsrq_stats.mean, -25, -5, 'var(--yellow)');
  _gauge('gauge-sinr', s.sinr_stats.mean, -15, 30, 'var(--orange)');
  const t = s.anomaly_count || 1;
  _w('bar-critical', (s.severity_distribution.critical / t * 100).toFixed(0));
  _w('bar-high',     (s.severity_distribution.high     / t * 100).toFixed(0));
  _w('bar-medium',   (s.severity_distribution.medium   / t * 100).toFixed(0));
  _txt('lbl-critical', s.severity_distribution.critical);
  _txt('lbl-high',     s.severity_distribution.high);
  _txt('lbl-medium',   s.severity_distribution.medium);
  if (REAL_ANOMALIES.length && _buf.length === 0) {
    const sorted = [...REAL_ANOMALIES].sort((a,b) => new Date(a.time) - new Date(b.time));
    _buf = sorted.map(r => r.ml_anomaly_score * 100);
  }
  drawChart(); drawAnomalyTypes(); drawAreaPie();
}

function _applyAlerts() {
  ALERTS.length = 0;
  REAL_ANOMALIES.slice(0,50).forEach(r => {
    ALERTS.push({
      id: r.measurement_id,
      severity: r.severity === 'low' ? 'medium' : r.severity,
      title: (r.anomaly_types[0] || 'ML Anomaly') + ' — ' + r.area_name,
      location: r.area_name + ', ' + r.district,
      root_cause: r.root_causes[0] || 'Unknown',
      cause_explanation: r.root_causes.join(' | ') || 'ML-detected anomaly',
      priority: r.severity,
      eta: r.severity==='critical'?'1-2 hours':r.severity==='high'?'2-4 hours':'4-8 hours',
      suggested_solution: r.root_causes.length ? r.root_causes : ['Investigate signal metrics'],
      affected_standards: ['TS 28.552', 'TS 32.111'],
      escalation_needed: r.severity === 'critical',
      additional_notes: 'RSRP:' + r.rsrp_dbm + ' RSRQ:' + r.rsrq_db + ' SINR:' + r.sinr_db,
      ts: new Date(r.time).getTime(),
      score: r.ml_anomaly_score,
      symptoms: r.anomaly_types,
      notified: r.severity==='critical'?['engineer','call_center','client']:r.severity==='high'?['engineer','call_center']:['call_center'],
    });
  });
  renderAlerts(document.getElementById('dashboard-alerts'), ALERTS.slice(0,3));
  renderAlerts(document.getElementById('alerts-list'), ALERTS);
  const b = document.getElementById('alert-badge-count');
  if (b) b.textContent = REAL_SUMMARY.anomaly_count || ALERTS.length;
}

function _applyModel() {
  if (!REAL_MODELS) return;
  const tbody = document.getElementById('model-metrics-table');
  if (!tbody) return;
  tbody.innerHTML = Object.entries(REAL_MODELS.metrics).map(([name, v]) =>
    '<tr><td>' + name + '</td>' +
    '<td><span class="badge ' + (v.f1_score>=0.8?'ok':v.f1_score>=0.6?'medium':'high') + '">' + (v.f1_score*100).toFixed(1) + '%</span></td>' +
    '<td>' + (v.precision*100).toFixed(1) + '%</td>' +
    '<td>' + (v.recall*100).toFixed(1) + '%</td>' +
    '<td>' + (v.accuracy*100).toFixed(1) + '%</td>' +
    '<td>' + (name===REAL_MODELS.best_model?'★':'') + '</td></tr>'
  ).join('');
  drawFeatureImportance();
}

// ── DOM HELPERS ────────────────────────────────────────────────────
function _txt(id, v)  { const e=document.getElementById(id); if(e) e.textContent=v; }
function _html(id, v) { const e=document.getElementById(id); if(e) e.innerHTML=v; }
function _w(id, pct)  { const e=document.getElementById(id); if(e) e.style.width=pct+'%'; }

function _gauge(id, val, min, max, color) {
  const svg = document.getElementById(id); if (!svg) return;
  const pct = Math.max(0, Math.min(1, (val-min)/(max-min)));
  const C = 188.4, off = C - pct*C;
  svg.innerHTML =
    '<circle cx="36" cy="36" r="30" fill="none" stroke="var(--bg-3)" stroke-width="6"/>' +
    '<circle cx="36" cy="36" r="30" fill="none" stroke="' + color + '" stroke-width="6"' +
    ' stroke-dasharray="' + C + '" stroke-dashoffset="' + off + '"' +
    ' stroke-linecap="round" transform="rotate(-90 36 36)"/>' +
    '<text x="36" y="40" text-anchor="middle" fill="var(--text-0)"' +
    ' font-size="10" font-family="IBM Plex Mono" font-weight="500">' + val.toFixed(1) + '</text>';
}

// ── CHARTS ────────────────────────────────────────────────────────
let _buf = [], _ticker = null, _range = '1H';

function drawChart(range) {
  if (range) _range = range;
  const svg = document.getElementById('main-chart'); if (!svg) return;
  const take = _range==='1H'?60:_range==='6H'?120:_buf.length||60;
  const pts = (_buf.length ? _buf : Array.from({length:60},()=>Math.random()*15)).slice(-take);
  _renderChart(svg, pts);
}

function _renderChart(svg, pts) {
  const W=600, H=200, PL=48, PT=10, PB=32, PR=10;
  const cW=W-PL-PR, cH=H-PT-PB;
  const xS = i => PL + (i/(pts.length-1||1))*cW;
  const yS = v => PT + cH - (v/100)*cH;
  const line = pts.map((v,i) => (i===0?'M':'L')+xS(i).toFixed(1)+','+yS(v).toFixed(1)).join(' ');
  const area = line+' L'+xS(pts.length-1).toFixed(1)+','+(PT+cH)+' L'+PL+','+(PT+cH)+' Z';
  let yL='', yTx='';
  [0,25,50,75,100].forEach(v => {
    const y = yS(v).toFixed(1);
    yL  += '<line x1="'+PL+'" y1="'+y+'" x2="'+(PL+cW)+'" y2="'+y+'" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 4"/>';
    yTx += '<text x="'+(PL-6)+'" y="'+(parseFloat(y)+4)+'" text-anchor="end" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">'+v+'</text>';
  });
  const st = Math.max(1, Math.floor(pts.length/6));
  let xTx = '';
  for (let i=0; i<pts.length; i+=st)
    xTx += '<text x="'+xS(i).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle" fill="var(--text-2)" font-size="9" font-family="IBM Plex Mono">'+i+'</text>';
  xTx += '<text x="'+xS(pts.length-1).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle" fill="var(--orange)" font-size="9" font-family="IBM Plex Mono">now</text>';
  let zones='', inZ=false, zS=0;
  pts.forEach((v,i) => {
    if (v>50&&!inZ){inZ=true;zS=i;}
    else if(v<=50&&inZ){zones+='<rect x="'+xS(zS).toFixed(1)+'" y="'+PT+'" width="'+(xS(i)-xS(zS)).toFixed(1)+'" height="'+cH+'" fill="rgba(232,69,10,0.08)"/>';inZ=false;}
  });
  svg.innerHTML =
    '<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0%" stop-color="var(--orange)" stop-opacity=".2"/>' +
    '<stop offset="100%" stop-color="var(--orange)" stop-opacity="0"/>' +
    '</linearGradient></defs>' + yL + zones +
    '<path d="'+area+'" fill="url(#ag)"/>' +
    '<path d="'+line+'" fill="none" stroke="var(--orange)" stroke-width="1.8" stroke-linejoin="round"/>' +
    '<line x1="'+PL+'" y1="'+PT+'" x2="'+PL+'" y2="'+(PT+cH)+'" stroke="var(--border-lit)" stroke-width="1"/>' +
    '<line x1="'+PL+'" y1="'+(PT+cH)+'" x2="'+(PL+cW)+'" y2="'+(PT+cH)+'" stroke="var(--border-lit)" stroke-width="1"/>' +
    yTx + xTx +
    '<text x="'+(PL+cW/2)+'" y="'+(PT+8)+'" text-anchor="middle" fill="var(--text-2)" font-size="8" font-family="IBM Plex Mono">Anomaly Score %</text>';
}

function startTicker() {
  if (_ticker) clearInterval(_ticker);
  _ticker = setInterval(() => {
    const svg = document.getElementById('main-chart'); if (!svg) return;
    const last = _buf.length ? _buf[_buf.length-1] : 10;
    _buf.push(Math.max(0, Math.min(100, last + (Math.random()-0.48)*5)));
    if (_buf.length > 500) _buf.shift();
    const take = _range==='1H'?60:_range==='6H'?120:_buf.length;
    _renderChart(svg, _buf.slice(-take));
  }, 1000);
}

function setChartRange(range, btn) {
  _range = range;
  document.querySelectorAll('.chart-time-btn').forEach(b=>{b.style.color='';b.style.borderColor='';});
  btn.style.color='var(--orange)'; btn.style.borderColor='var(--orange)';
  drawChart(range);
}

function drawSparkline(id, min, max, color) {
  const svg = document.getElementById(id); if (!svg) return;
  let v=(min+max)/2;
  const pts = Array.from({length:20},()=>{v+=(Math.random()-0.5)*(max-min)/4;v=Math.max(min,Math.min(max,v));return v;});
  const mn=Math.min(...pts), mx=Math.max(...pts);
  const line = pts.map((p,i)=>(i===0?'M':'L')+(i/19*80).toFixed(1)+','+(40-((p-mn)/(mx-mn+1))*36-2).toFixed(1)).join(' ');
  svg.innerHTML = '<path d="'+line+'" fill="none" stroke="'+(color||'var(--orange)')+'\" stroke-width=\"1.5\"/>';
}

function drawAnomalyTypes() {
  const svg = document.getElementById('anomaly-types-chart'); if (!svg||!REAL_SUMMARY) return;
  const entries = Object.entries(REAL_SUMMARY.anomaly_types_distribution).slice(0,6).sort((a,b)=>b[1]-a[1]);
  const maxV = entries[0]?.[1]||1;
  const W=500, bH=22, gap=8, lW=220, pad=10, tH=entries.length*(bH+gap)+2*pad;
  const clr=['var(--orange)','var(--red)','var(--yellow)','var(--blue)','var(--green)','var(--orange-hi)'];
  let bars='';
  entries.forEach(([name,val],i) => {
    const bW=((val/maxV)*(W-lW-50)).toFixed(0), y=pad+i*(bH+gap), n=name.length>28?name.slice(0,28)+'…':name;
    bars += '<text x="'+(lW-6)+'" y="'+(y+bH/2+4)+'" text-anchor="end" fill="var(--text-1)" font-size="9" font-family="IBM Plex Mono">'+n+'</text>' +
            '<rect x="'+lW+'" y="'+y+'" width="'+bW+'" height="'+bH+'" rx="3" fill="'+clr[i]+'" opacity=".8"/>' +
            '<text x="'+(lW+parseFloat(bW)+6)+'" y="'+(y+bH/2+4)+'" fill="var(--text-0)" font-size="9" font-family="IBM Plex Mono" font-weight="500">'+val+'</text>';
  });
  svg.setAttribute('viewBox','0 0 '+W+' '+tH); svg.setAttribute('height',tH); svg.innerHTML=bars;
}

function drawAreaPie() {
  const svg = document.getElementById('area-chart'); if (!svg||!REAL_SUMMARY) return;
  const entries=Object.entries(REAL_SUMMARY.top_anomaly_areas), total=entries.reduce((s,[,v])=>s+v,0);
  const clr=['var(--orange)','var(--red)','var(--yellow)','var(--blue)'], R=60, cx=80, cy=70;
  let a=-Math.PI/2, sl='', lg='';
  entries.forEach(([name,val],i)=>{
    const ang=(val/total)*2*Math.PI, ea=a+ang;
    const x1=(cx+R*Math.cos(a)).toFixed(1),y1=(cy+R*Math.sin(a)).toFixed(1);
    const x2=(cx+R*Math.cos(ea)).toFixed(1),y2=(cy+R*Math.sin(ea)).toFixed(1);
    sl+='<path d="M'+cx+','+cy+' L'+x1+','+y1+' A'+R+','+R+' 0 '+(ang>Math.PI?1:0)+',1 '+x2+','+y2+' Z" fill="'+clr[i]+'" opacity=".85"/>';
    lg+='<rect x="165" y="'+(10+i*22)+'" width="10" height="10" rx="2" fill="'+clr[i]+'"/>' +
        '<text x="180" y="'+(20+i*22)+'" fill="var(--text-1)" font-size="9" font-family="IBM Plex Mono">'+name+' ('+val+')</text>';
    a=ea;
  });
  svg.innerHTML=sl+lg+'<text x="'+cx+'" y="'+(cy+4)+'" text-anchor="middle" fill="var(--text-0)" font-size="9" font-family="IBM Plex Mono" font-weight="600">'+total+' total</text>';
}

function drawFeatureImportance() {
  const svg = document.getElementById('feature-importance-chart'); if (!svg||!REAL_MODELS) return;
  const feat=REAL_MODELS.feature_importance_xgb.slice(0,8), maxI=feat[0]?.importance||1;
  const W=440, bH=20, gap=7, lW=160, pad=8, tH=feat.length*(bH+gap)+2*pad;
  let bars='';
  feat.forEach((f,i)=>{
    const bW=((f.importance/maxI)*(W-lW-60)).toFixed(0), y=pad+i*(bH+gap);
    bars+='<text x="'+(lW-6)+'" y="'+(y+bH/2+4)+'" text-anchor="end" fill="var(--text-1)" font-size="9" font-family="IBM Plex Mono">'+f.feature+'</text>' +
          '<rect x="'+lW+'" y="'+y+'" width="'+bW+'" height="'+bH+'" rx="3" fill="var(--orange)" opacity="'+(0.5+f.importance/maxI*0.5)+'"/>' +
          '<text x="'+(lW+parseFloat(bW)+6)+'" y="'+(y+bH/2+4)+'" fill="var(--text-0)" font-size="9" font-family="IBM Plex Mono">'+(f.importance*100).toFixed(1)+'%</text>';
  });
  svg.setAttribute('viewBox','0 0 '+W+' '+tH); svg.setAttribute('height',tH); svg.innerHTML=bars;
}

// ── CLOCK & NAV ────────────────────────────────────────────────────
function updateClock() {
  const v = new Date().toTimeString().slice(0,8);
  ['clock','mobile-clock'].forEach(id=>{const e=document.getElementById(id);if(e)e.textContent=v;});
}
setInterval(updateClock,1000); updateClock();

function showPage(name, btn) {
  document.querySelectorAll('.page.main').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  const pg=document.getElementById('page-'+name); if(pg) pg.classList.add('active');
  if(btn) btn.classList.add('active');
  closeMobileNav();
}
function toggleTheme() { document.body.classList.toggle('light'); localStorage.setItem('theme',document.body.classList.contains('light')?'light':'dark'); }
function toggleMobileNav(btn) { const tb=document.querySelector('.topbar'); if(!tb) return; const o=tb.classList.toggle('menu-open'); if(btn) btn.setAttribute('aria-expanded',String(o)); }
function closeMobileNav() { const tb=document.querySelector('.topbar'); if(!tb) return; tb.classList.remove('menu-open'); const t=document.querySelector('.mobile-nav-toggle'); if(t) t.setAttribute('aria-expanded','false'); }

function timeAgo(ts) { const m=Math.floor((Date.now()-ts)/60000); if(m<60) return m+'m ago'; const h=Math.floor(m/60); if(h<24) return h+'h ago'; return Math.floor(h/24)+'d ago'; }

function severityIcon(s) {
  if (s==='critical') return '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
  if (s==='high')     return '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
  return '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>';
}

// ── ALERTS ────────────────────────────────────────────────────────
function renderAlerts(container, alerts) {
  if (!container) return;
  if (!alerts.length) { container.innerHTML='<div class="empty-state"><p>No alerts found</p></div>'; return; }
  container.innerHTML = alerts.map(a =>
    '<div class="alert-item '+a.severity+'" onclick="openPanel('+a.id+')">' +
    '<div class="alert-icon">'+severityIcon(a.severity)+'</div>' +
    '<div class="alert-body"><div class="alert-title">'+a.title+'</div>' +
    '<div class="alert-meta"><span>'+a.location+'</span><span>'+a.root_cause+'</span><span>'+timeAgo(a.ts)+'</span></div></div>' +
    '<div class="alert-score">'+Math.round(a.score*100)+'%</div></div>'
  ).join('');
}
function filterAlerts(f, btn) {
  currentFilter=f;
  document.querySelectorAll('#page-alerts .btn[onclick^="filterAlerts"]').forEach(b=>b.className='btn btn-ghost btn-sm');
  if(btn) btn.className='btn btn-primary btn-sm';
  renderAlerts(document.getElementById('alerts-list'), f==='all'?ALERTS:ALERTS.filter(a=>a.severity===f));
}
function searchAlerts(q) {
  const lq=q.toLowerCase(), base=currentFilter==='all'?ALERTS:ALERTS.filter(a=>a.severity===currentFilter);
  renderAlerts(document.getElementById('alerts-list'), base.filter(a=>a.title.toLowerCase().includes(lq)||a.location.toLowerCase().includes(lq)||a.root_cause.toLowerCase().includes(lq)));
}
function openPanel(id) {
  const a=ALERTS.find(x=>x.id===id); if(!a) return;
  document.getElementById('panel-title').textContent=a.title;
  document.getElementById('panel-body').innerHTML=
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span class="badge '+a.severity+'">'+a.severity.toUpperCase()+'</span><span style="font-size:.75rem;color:var(--text-2);">'+timeAgo(a.ts)+'</span></div>'+
    '<div style="margin-bottom:14px;"><div style="font-size:.68rem;color:var(--text-2);text-transform:uppercase;letter-spacing:.09em;margin-bottom:6px;">Anomaly Score</div>'+
    '<div style="display:flex;align-items:center;gap:10px;"><div class="score-meter" style="flex:1;"><div class="score-fill" style="width:'+Math.round(a.score*100)+'%"></div></div><span>'+Math.round(a.score*100)+'%</span></div></div>'+
    '<div class="detail-row"><div class="detail-key">Location</div><div class="detail-val">'+a.location+'</div></div>'+
    '<div class="detail-row"><div class="detail-key">Root Cause</div><div class="detail-val">'+a.root_cause+'</div></div>'+
    '<div class="detail-row"><div class="detail-key">Explanation</div><div class="detail-val" style="color:var(--text-1);font-size:.8rem;">'+a.cause_explanation+'</div></div>'+
    '<div class="detail-row"><div class="detail-key">ETA</div><div class="detail-val">'+a.eta+'</div></div>'+
    '<div class="detail-row"><div class="detail-key">Escalation</div><div class="detail-val" style="color:'+(a.escalation_needed?'var(--red)':'var(--green)')+';">'+(a.escalation_needed?'Yes — NOC':'No')+'</div></div>'+
    '<div class="detail-row"><div class="detail-key">Steps</div><div class="detail-val"><div class="solution-steps">'+a.suggested_solution.map((s,i)=>'<div class="solution-step"><span class="step-num">'+(i+1)+'</span><span>'+s+'</span></div>').join('')+'</div></div></div>'+
    '<div class="detail-row"><div class="detail-key">Notes</div><div class="detail-val" style="color:var(--text-2);font-size:.78rem;">'+a.additional_notes+'</div></div>'+
    '<div style="margin-top:20px;"><button class="btn btn-ghost" onclick="closePanel()">Close</button></div>';
  document.getElementById('detail-panel').classList.add('open');
}
function closePanel() { document.getElementById('detail-panel').classList.remove('open'); }

// ── RAG FILES ─────────────────────────────────────────────────────
function renderRagFiles() {
  const tb=document.getElementById('rag-files-table'); if(!tb) return;
  tb.innerHTML=RAG_FILES.map(f=>'<tr><td>'+f.name+'</td><td><span class="badge ok">'+f.type+'</span></td><td>'+f.chunks+'</td><td><button class="btn btn-danger btn-sm" onclick="deleteRagFile(\''+f.name+'\',this)">Delete</button></td></tr>').join('');
}
function deleteRagFile(name,btn) {
  const row=btn.closest('tr'); row.style.opacity='.3'; row.style.transition='opacity .3s';
  setTimeout(()=>{const i=RAG_FILES.findIndex(f=>f.name===name);if(i>-1)RAG_FILES.splice(i,1);renderRagFiles();},400);
}
function handleDragOver(e){e.preventDefault();document.getElementById('upload-zone').classList.add('drag-over');}
function handleDragLeave(){document.getElementById('upload-zone').classList.remove('drag-over');}
function handleDrop(e){e.preventDefault();document.getElementById('upload-zone').classList.remove('drag-over');handleFiles(e.dataTransfer.files);}
function handleFiles(files){Array.from(files).forEach(f=>{uploadQueue.push(f);addFileToQueue(f);});}
function addFileToQueue(file) {
  const el=document.createElement('div'); el.className='file-item'; el.id='file-'+file.name.replace(/\W/g,'_');
  el.innerHTML='<div class="file-icon-wrap"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><div class="file-info"><div class="file-name">'+file.name+'</div><div class="file-size">'+(file.size/1024).toFixed(0)+' KB</div></div><span class="badge medium">Queued</span>';
  document.getElementById('upload-queue').appendChild(el);
}
function clearQueue(){uploadQueue=[];document.getElementById('upload-queue').innerHTML='';document.getElementById('ingest-progress').classList.remove('visible');}
function startIngest() {
  if(!uploadQueue.length){alert('Add files first');return;}
  document.getElementById('ingest-progress').classList.add('visible');
  const steps=['step-load','step-chunk','step-embed','step-store'],bar=document.getElementById('ingest-bar');
  let i=0;
  function nx(){
    if(i>0){const p=document.getElementById(steps[i-1]);p.classList.remove('active');p.classList.add('done');}
    if(i>=steps.length){bar.style.width='100%';uploadQueue.forEach(f=>{const el=document.getElementById('file-'+f.name.replace(/\W/g,'_'));if(el){const b=el.querySelector('.badge');b.className='badge ok';b.textContent='Indexed';}RAG_FILES.push({name:f.name,type:f.name.split('.').pop().toUpperCase(),chunks:Math.floor(Math.random()*200+50),size:(f.size/1024).toFixed(0)+' KB'});});uploadQueue=[];renderRagFiles();return;}
    document.getElementById(steps[i]).classList.add('active');bar.style.width=((i+1)/steps.length*100)+'%';i++;setTimeout(nx,1200+Math.random()*600);
  }
  nx();
}

// ── CONFIG ────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res=await fetch(API_BASE+'/config'); if(!res.ok) return;
    const c=await res.json();
    const map={engineer:'engineer_email',callcenter:'callcenter_email',client:'client_email'};
    Object.entries(map).forEach(([role,key])=>{
      const ef=document.getElementById(role+'-email'),ed=document.getElementById(role+'-email-display'),val=c[key];
      if(ef&&val)ef.value=val; if(ed)ed.textContent=val||'(not set)';
    });
    const ss=document.getElementById('smtp-sender'); if(ss&&c.smtp_sender)ss.value=c.smtp_sender;
  } catch(_){}
}
function updateEmail(role,val){const e=document.getElementById(role+'-email-display');if(e)e.textContent=val||'(not set)';}
function toggleRecipient(role,cb){const e=document.getElementById(role+'-email-display');if(e)e.style.textDecoration=cb.checked?'none':'line-through';}
function switchTemplate(name,btn){document.querySelectorAll('.tmpl-tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tmpl-content').forEach(c=>c.style.display='none');btn.classList.add('active');document.getElementById('tmpl-'+name).style.display='block';}
function saveTemplates(){const btn=event.currentTarget,orig=btn.innerHTML;btn.innerHTML='Saved';btn.style.background='var(--green)';setTimeout(()=>{btn.innerHTML=orig;btn.style.background='';},1800);}
async function testSmtp(){
  const btn=event.currentTarget,orig=btn.innerHTML;btn.textContent='Sending…';btn.disabled=true;
  try{const res=await fetch(API_BASE+'/test-email',{method:'POST'}),d=await res.json();btn.textContent=res.ok?'Sent to '+d.to:'Error: '+d.detail;btn.style.color=res.ok?'var(--green)':'var(--red)';}
  catch(_){btn.textContent='API unreachable';btn.style.color='var(--red)';}
  setTimeout(()=>{btn.innerHTML=orig;btn.style.color='';btn.disabled=false;},3500);
}

// ── CHAT ──────────────────────────────────────────────────────────
async function sendChat() {
  const inp=document.getElementById('chat-input'),q=inp.value.trim(); if(!q) return;
  inp.value=''; document.getElementById('chat-suggestions').style.display='none';
  _msg(q,'user'); const lid=_msg('Thinking...','assistant loading');
  try {
    const res=await fetch(API_BASE+'/query/general',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});
    if(!res.ok){const e=await res.json().catch(()=>({}));_upd(lid,'Error: '+(e.detail||res.status));return;}
    const d=await res.json(); _upd(lid,d.answer||'No response from RAG.');
  } catch(_){_upd(lid,'Cannot reach the RAG API.');}
}
function sendSuggestion(btn){document.getElementById('chat-input').value=btn.textContent;btn.remove();sendChat();}
function _msg(text,cls){const id='msg-'+Date.now(),el=document.getElementById('chat-messages');el.innerHTML+='<div class="chat-msg '+cls+'" id="'+id+'"><div class="chat-bubble">'+text+'</div></div>';el.scrollTop=el.scrollHeight;return id;}
function _upd(id,text){const e=document.getElementById(id);if(!e)return;e.className='chat-msg assistant';e.querySelector('.chat-bubble').textContent=text;}

// ── DEMO ──────────────────────────────────────────────────────────
const DEMO = {
  critical:{severity:'critical',ml_anomaly_score:0.91,location:'Westbahnhof, Vienna',cell_id:'107011',anomaly_types:['High path loss (123 dB)','RSRP deviation (-113.4 dBm)'],root_causes:['Extreme signal weakness - coverage hole','Excessive propagation loss - indoor obstruction'],rsrp_dbm:-113.4,rsrq_db:-24.3,sinr_db:-12.7,dl_throughput_mbps:0.0},
  high:    {severity:'high',    ml_anomaly_score:0.74,location:'Mariahilfer Strasse, Vienna',cell_id:'129795',anomaly_types:['RSRQ deviation (-18.9 dB)','Signal quality degradation'],root_causes:['Severe interference - PCI conflict or external RF source'],rsrp_dbm:-102.6,rsrq_db:-18.9,sinr_db:-4.3,dl_throughput_mbps:7.4},
  medium:  {severity:'medium',  ml_anomaly_score:0.52,location:'Karlsplatz, Vienna',cell_id:'163341',anomaly_types:['ML-detected statistical anomaly'],root_causes:['Pattern deviation detected by AI'],rsrp_dbm:-97.4,rsrq_db:-14.4,sinr_db:0.4,dl_throughput_mbps:23.5},
};
let _demoRec = null;
function runDemo(type) {
  if(type==='replay'){const r=REAL_ANOMALIES.find(x=>x.severity==='critical')||REAL_ANOMALIES[0];if(!r){document.getElementById('demo-status').textContent='No real data loaded';return;}_demoRec=[{severity:r.severity,ml_anomaly_score:r.ml_anomaly_score,location:r.area_name+', '+r.district,cell_id:String(r.cell_id),anomaly_types:r.anomaly_types,root_causes:r.root_causes,rsrp_dbm:r.rsrp_dbm,rsrq_db:r.rsrq_db,sinr_db:r.sinr_db,dl_throughput_mbps:r.dl_throughput_mbps}];}
  else{_demoRec=[DEMO[type]];}
  document.getElementById('demo-preview').textContent=JSON.stringify(_demoRec[0],null,2);
  document.getElementById('demo-run-btn').disabled=false;
  document.getElementById('demo-status').textContent='Ready — click Run & Analyze';
  document.getElementById('demo-result').style.display='none';
}
async function submitDemo() {
  if(!_demoRec) return;
  const btn=document.getElementById('demo-run-btn'),st=document.getElementById('demo-status');
  btn.disabled=true;btn.textContent='Analyzing…';st.textContent='Sending to RAG pipeline…';st.style.color='var(--orange)';
  try {
    const res=await fetch(API_BASE+'/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(_demoRec)});
    const d=await res.json(),rag=d.rag_result||{},notif=d.notification||{};
    document.getElementById('demo-cause').textContent=rag.cause_explanation||'No explanation (run /ingest first to load 3GPP specs)';
    document.getElementById('demo-eta').textContent=rag.estimated_resolution_time?'ETA: '+rag.estimated_resolution_time:'';
    const nr=notif.recipients_notified||[];
    document.getElementById('demo-notified').innerHTML=nr.length?nr.map(r=>'<span class="badge ok" style="margin-right:4px;">'+r+'</span>').join(''):'<span style="color:var(--text-2);">No emails — check Settings</span>';
    document.getElementById('demo-errors').textContent=(notif.errors||[]).join(' | ');
    const steps=rag.suggested_solution||[];
    document.getElementById('demo-steps').innerHTML=steps.length?steps.map((s,i)=>'<div style="margin-bottom:4px;"><span style="color:var(--orange);font-weight:600;">'+(i+1)+'.</span> '+s+'</div>').join(''):'No steps returned.';
    document.getElementById('demo-result').style.display='block';
    st.textContent='Done — '+d.processed+' record, '+nr.length+' notified';st.style.color='var(--green)';
  } catch(e){st.textContent='Error: '+e.message;st.style.color='var(--red)';}
  btn.disabled=false;btn.textContent='Run & Analyze';
}

// ── INIT ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (localStorage.getItem('theme')==='light') document.body.classList.add('light');
  drawChart(); drawSparkline('spark-throughput',700,1000,'var(--green)');
  renderAlerts(document.getElementById('dashboard-alerts'), ALERTS.slice(0,3));
  renderAlerts(document.getElementById('alerts-list'), ALERTS);
  renderRagFiles();
  loadRealData(); loadConfig(); startTicker();
});
