let civicMap = null;
let civicTileLayer = null;
let civicLayers = [];
let civicMarkers = [];
let civicCharts = {};
let civicMapMode = 'auto';
let tileErrorCount = 0;

let civicLiveLocation = null;
let civicLiveLayer = null;
const CIVICOS_LOCATION_KEY = 'civicos-live-location-v2';

function getStoredCivicLocation(){
  try{
    const raw=localStorage.getItem(CIVICOS_LOCATION_KEY);
    if(!raw) return null;
    const item=JSON.parse(raw);
    if(!item || !validCoordinate(item.lat) || !validCoordinate(item.lon)) return null;
    return item;
  }catch(_e){ return null; }
}

function rememberCivicLocation(lat,lon,address='',accuracy=null,shortLabel=''){
  if(!validCoordinate(lat) || !validCoordinate(lon)) return;
  const item={
    lat:Number(lat),lon:Number(lon),address:String(address||''),
    accuracy:Number.isFinite(Number(accuracy))?Number(accuracy):null,
    shortLabel:String(shortLabel||''),savedAt:Date.now()
  };
  civicLiveLocation=item;
  try{ localStorage.setItem(CIVICOS_LOCATION_KEY,JSON.stringify(item)); }catch(_e){}
  updateAdminLiveArea(item,'stored');
  renderAdminLiveLocationMarker(false);
}

function adminLocationLabel(item){
  if(!item) return 'Live location unavailable';
  if(item.shortLabel) return item.shortLabel;
  if(item.address){
    const first=item.address.split(',').map(v=>v.trim()).filter(Boolean).slice(0,2).join(', ');
    if(first) return first;
  }
  return `${Number(item.lat).toFixed(4)}, ${Number(item.lon).toFixed(4)}`;
}

function updateAdminLiveArea(item,state='live'){
  const name=document.getElementById('adminAreaName');
  const pill=document.getElementById('adminLiveArea');
  if(!name || !pill) return;
  if(!item){
    name.textContent='Live location unavailable';
    pill.dataset.locationState='unavailable';
    pill.title='Live GPS could not be read. Allow location permission, use localhost/HTTPS, or capture a location from the Report page.';
    return;
  }
  name.textContent=adminLocationLabel(item);
  pill.dataset.locationState=state;
  const accuracy=item.accuracy?` · accuracy ±${Math.round(item.accuracy)} m`:'';
  const source=state==='live'?'Live device location':'Last confirmed device location';
  pill.title=`${source}${accuracy}\n${item.address||`${item.lat}, ${item.lon}`}\nClick to center the map.`;
}

async function reverseCivicLocation(lat,lon){
  try{
    const res=await fetch(`/api/reverse-geocode?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,{headers:{Accept:'application/json'},cache:'no-store'});
    const data=await res.json();
    return {
      address:data.exact_address||data.display_name||`GPS location: ${Number(lat).toFixed(7)}, ${Number(lon).toFixed(7)}`,
      shortLabel:data.short_label||'',
    };
  }catch(_e){
    return {address:`GPS location: ${Number(lat).toFixed(7)}, ${Number(lon).toFixed(7)}`,shortLabel:''};
  }
}

function renderAdminLiveLocationMarker(center=false){
  const item=civicLiveLocation || getStoredCivicLocation();
  if(!item || !civicMap || typeof L==='undefined' || civicMapMode==='fallback') return;
  if(civicLiveLayer){ try{ civicMap.removeLayer(civicLiveLayer); }catch(_e){} }
  civicLiveLayer=L.circleMarker([Number(item.lat),Number(item.lon)],{
    radius:9,color:'#ffffff',weight:3,fillColor:'#111827',fillOpacity:.96
  }).addTo(civicMap);
  civicLiveLayer.bindTooltip('Your live location',{direction:'top',offset:[0,-8]});
  civicLiveLayer.bindPopup(`<div class="civic-popup"><b>Your live location</b><span>${escapeHtml(item.address||'Exact GPS coordinates captured')}</span><span>${Number(item.lat).toFixed(6)}, ${Number(item.lon).toFixed(6)}</span></div>`);
  if(center) civicMap.setView([Number(item.lat),Number(item.lon)],15,{animate:true});
}

function centerAdminMapOnLiveLocation(forceRefresh=false){
  if(forceRefresh) refreshAdminLiveLocation(true);
  const item=civicLiveLocation || getStoredCivicLocation();
  if(item){
    civicLiveLocation=item;
    renderAdminLiveLocationMarker(true);
  }
}

function refreshAdminLiveLocation(force=false){
  const pill=document.getElementById('adminLiveArea');
  if(!pill) return;
  const stored=getStoredCivicLocation();
  if(stored){
    civicLiveLocation=stored;
    updateAdminLiveArea(stored,'stored');
  }else{
    const name=document.getElementById('adminAreaName');
    if(name) name.textContent='Locating…';
  }

  const localhost=['localhost','127.0.0.1','::1'].includes(window.location.hostname);
  const gpsAllowed=Boolean(navigator.geolocation && (window.isSecureContext || localhost));
  if(!gpsAllowed){
    if(!stored) updateAdminLiveArea(null,'unavailable');
    return;
  }

  navigator.geolocation.getCurrentPosition(async pos=>{
    const lat=pos.coords.latitude, lon=pos.coords.longitude, accuracy=pos.coords.accuracy;
    const resolved=await reverseCivicLocation(lat,lon);
    const item={lat:Number(lat),lon:Number(lon),address:resolved.address,shortLabel:resolved.shortLabel,accuracy:Number(accuracy)||null,savedAt:Date.now()};
    civicLiveLocation=item;
    try{localStorage.setItem(CIVICOS_LOCATION_KEY,JSON.stringify(item));}catch(_e){}
    updateAdminLiveArea(item,'live');
    renderAdminLiveLocationMarker(force);
  },()=>{
    if(stored) updateAdminLiveArea(stored,'stored'); else updateAdminLiveArea(null,'unavailable');
  },{enableHighAccuracy:true,timeout:15000,maximumAge:force?0:30000});
}

function initAdminLiveLocation(){
  if(document.getElementById('adminLiveArea')) refreshAdminLiveLocation(false);
}

function getLocation(){
  if(!navigator.geolocation){ alert('Geolocation is not supported by this browser.'); return; }
  const button = document.querySelector('[onclick="getLocation()"]');
  if(button){ button.textContent='Getting location…'; button.disabled=true; }
  navigator.geolocation.getCurrentPosition(pos=>{
    const lat=document.getElementById('lat');
    const lon=document.getElementById('lon');
    if(lat) lat.value=pos.coords.latitude.toFixed(6);
    if(lon) lon.value=pos.coords.longitude.toFixed(6);
    if(button){ button.textContent='Location Captured ✓'; button.disabled=false; }
  },()=>{
    if(button){ button.textContent='Use My Location'; button.disabled=false; }
    alert('Location permission was not available. You can type latitude and longitude manually.');
  },{enableHighAccuracy:true,timeout:10000,maximumAge:60000});
}

function colorForDepartment(dept){
  return {water:'#0ea5e9',electricity:'#f59e0b',road:'#64748b',police:'#ef4444',health:'#16a34a',fire:'#dc2626'}[dept] || '#0f9b8e';
}

function escapeHtml(value){
  return String(value ?? '').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function validCoordinate(value){
  const n=Number(value);
  return Number.isFinite(n);
}

function setMapStatus(message='',kind='info'){
  const overlay=document.getElementById('mapStatusOverlay');
  if(!overlay) return;
  if(!message){ overlay.hidden=true; overlay.textContent=''; overlay.className='map-status-overlay'; return; }
  overlay.hidden=false;
  overlay.textContent=message;
  overlay.className=`map-status-overlay ${kind}`;
}

function updateMapCount(markers){
  const count=document.getElementById('mapMarkerCount');
  if(!count) return;
  const escalated=markers.filter(m=>m.escalated && m.status!=='Resolved').length;
  count.innerHTML=`<b>${markers.length}</b> mapped issue${markers.length===1?'':'s'}${escalated?` · <strong>${escalated} escalated</strong>`:''}`;
}

function destroyChart(id){
  if(civicCharts[id] && typeof civicCharts[id].destroy === 'function') civicCharts[id].destroy();
  delete civicCharts[id];
}

function drawCanvasFallback(el, labels, data, label){
  const parent = el.parentElement;
  if(!parent) return;
  el.style.display='none';
  let fallback = parent.querySelector('.chart-fallback');
  if(!fallback){
    fallback=document.createElement('div');
    fallback.className='chart-fallback';
    parent.appendChild(fallback);
  }
  const max=Math.max(...data.map(Number),1);
  fallback.innerHTML=`<div class="fallback-chart-title">${escapeHtml(label)}</div>` + labels.map((name,i)=>{
    const val=Number(data[i]||0);
    const width=Math.max(3,Math.round((val/max)*100));
    return `<div class="fallback-bar-row"><span>${escapeHtml(name)}</span><div class="fallback-bar-track"><i style="width:${width}%"></i></div><b>${val}${label.includes('%')?'%':''}</b></div>`;
  }).join('');
}

function drawChart(id, type, labels, data, label){
  const el=document.getElementById(id);
  if(!el) return;
  if(typeof Chart === 'undefined'){
    drawCanvasFallback(el,labels,data,label);
    return;
  }
  el.style.display='block';
  const parentFallback=el.parentElement?.querySelector('.chart-fallback');
  if(parentFallback) parentFallback.remove();
  destroyChart(id);
  civicCharts[id]=new Chart(el,{
    type,
    data:{labels,datasets:[{label,data,borderRadius:10,backgroundColor:'rgba(15,155,142,.78)',borderColor:'#0f9b8e',borderWidth:1.5}]},
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{displayColors:false}},
      scales:type==='doughnut'?{}:{
        x:{grid:{display:false},ticks:{color:'#52657b',font:{weight:'700'}}},
        y:{beginAtZero:true,max:label.includes('%')?100:undefined,grid:{color:'rgba(148,163,184,.18)'},ticks:{precision:0,color:'#52657b'}}
      }
    }
  });
}

function filteredMarkers(){
  const dept=document.getElementById('mapDepartmentFilter')?.value || 'all';
  const status=document.getElementById('mapStatusFilter')?.value || 'all';
  return civicMarkers.filter(m=>{
    if(!validCoordinate(m.lat) || !validCoordinate(m.lon)) return false;
    if(dept !== 'all' && m.department !== dept) return false;
    if(status !== 'all' && m.status !== status) return false;
    return true;
  });
}

function removeLeafletMap(){
  if(civicMap){
    try{ civicMap.remove(); }catch(_e){}
  }
  civicMap=null;
  civicTileLayer=null;
  civicLayers=[];
}

function renderFallbackMap(reason='Offline-safe map view'){
  civicMapMode='fallback';
  removeLeafletMap();
  const el=document.getElementById('adminMap');
  if(!el) return;
  const markers=filteredMarkers();
  updateMapCount(markers);
  setMapStatus('', 'info');
  if(!markers.length){
    el.innerHTML='<div class="fallback-map empty"><b>No mapped issues match these filters.</b><span>Change department or status filters.</span></div>';
    return;
  }
  const lats=markers.map(m=>Number(m.lat)), lons=markers.map(m=>Number(m.lon));
  let minLat=Math.min(...lats), maxLat=Math.max(...lats), minLon=Math.min(...lons), maxLon=Math.max(...lons);
  if(minLat===maxLat){minLat-=.02;maxLat+=.02}
  if(minLon===maxLon){minLon-=.02;maxLon+=.02}
  const dots=markers.map(m=>{
    const x=8+84*((Number(m.lon)-minLon)/(maxLon-minLon));
    const y=8+78*(1-((Number(m.lat)-minLat)/(maxLat-minLat)));
    const size=m.escalated?26:Math.max(15,Math.min(23,Number(m.priority)/4.8));
    const c=m.escalated?'#dc2626':colorForDepartment(m.department);
    return `<a class="fallback-map-dot" aria-label="Complaint ${m.id}: ${escapeHtml(m.title)}" title="#${m.id} ${escapeHtml(m.title)}" href="/complaint/${m.id}" style="left:${x}%;top:${y}%;width:${size}px;height:${size}px;background:${c}"><span>#${m.id}</span></a>`;
  }).join('');
  el.innerHTML=`<div class="fallback-map">
    <div class="fallback-map-grid"></div>
    <div class="fallback-road road-a"></div><div class="fallback-road road-b"></div><div class="fallback-road road-c"></div><div class="fallback-road road-d"></div>
    <span class="fallback-place place-a">Kopargaon Area</span><span class="fallback-place place-b">Civic Ward Cluster</span>
    ${dots}
    <div class="fallback-map-note"><b>Civic Intelligence Map</b><span>${escapeHtml(reason)} · complaint positions preserved from latitude / longitude</span></div>
  </div>`;
}

function switchToFallback(reason){
  if(civicMapMode==='fallback') return;
  renderFallbackMap(reason || 'Map tiles unavailable');
}

function createLeafletMap(){
  const el=document.getElementById('adminMap');
  if(!el || typeof L === 'undefined') return false;
  try{
    el.innerHTML='';
    civicMapMode='leaflet';
    tileErrorCount=0;
    const savedLive=civicLiveLocation || getStoredCivicLocation();
    const initialCenter=savedLive?[Number(savedLive.lat),Number(savedLive.lon)]:[20.5937,78.9629];
    civicMap=L.map('adminMap',{scrollWheelZoom:false,zoomControl:true,preferCanvas:true,attributionControl:true}).setView(initialCenter,savedLive?13:5);
    civicTileLayer=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
      attribution:'© OpenStreetMap contributors',
      maxZoom:19,
      crossOrigin:true
    });
    civicTileLayer.on('tileerror',()=>{
      tileErrorCount += 1;
      if(tileErrorCount===3) setMapStatus('Map tiles are loading slowly. Complaint markers will remain available.','warning');
      if(tileErrorCount>=10) switchToFallback('Live OpenStreetMap tiles unavailable');
    });
    civicTileLayer.on('load',()=>setMapStatus('', 'info'));
    civicTileLayer.addTo(civicMap);
    civicMap.on('moveend zoomend',()=>setTimeout(()=>civicMap?.invalidateSize({pan:false}),40));
    return true;
  }catch(err){
    console.error('Map initialization failed:',err);
    removeLeafletMap();
    return false;
  }
}

function focusMapToMarkers(markers){
  if(!civicMap || typeof L==='undefined' || !markers.length) return;
  if(markers.length===1){
    civicMap.setView([Number(markers[0].lat),Number(markers[0].lon)],14,{animate:false});
    return;
  }
  const bounds=L.latLngBounds(markers.map(m=>[Number(m.lat),Number(m.lon)]));
  if(bounds.isValid()) civicMap.fitBounds(bounds,{padding:[45,45],maxZoom:13,animate:false});
}

function renderMap(markers){
  const el=document.getElementById('adminMap');
  if(!el) return;
  civicMarkers=(markers||[]).filter(m=>validCoordinate(m.lat)&&validCoordinate(m.lon));
  if(typeof L==='undefined'){
    renderFallbackMap('Offline-safe view: Leaflet library unavailable');
    return;
  }
  if(!civicMap && !createLeafletMap()){
    renderFallbackMap('Offline-safe view: map initialization unavailable');
    return;
  }
  applyMapFilters();
  renderAdminLiveLocationMarker(false);
  setTimeout(()=>civicMap?.invalidateSize({pan:false}),250);
  setTimeout(()=>civicMap?.invalidateSize({pan:false}),900);
}

function applyMapFilters(){
  const markers=filteredMarkers();
  updateMapCount(markers);
  if(civicMapMode==='fallback' || typeof L==='undefined' || !civicMap){
    renderFallbackMap(civicMapMode==='fallback'?'Offline-safe map view':'Offline-safe view: live map unavailable');
    return;
  }
  civicLayers.forEach(layer=>{try{civicMap.removeLayer(layer)}catch(_e){}});
  civicLayers=[];
  setMapStatus('', 'info');
  if(!markers.length){
    setMapStatus('No mapped issues match the selected filters.','empty');
    return;
  }
  markers.forEach(m=>{
    const isEscalated=Boolean(m.escalated && m.status!=='Resolved');
    const color=isEscalated?'#dc2626':colorForDepartment(m.department);
    const layer=L.circleMarker([Number(m.lat),Number(m.lon)],{
      radius:isEscalated?14:Math.max(8,Math.min(14,Number(m.priority||0)/8)),
      color:'#ffffff',
      fillColor:color,
      fillOpacity:.92,
      weight:3
    }).addTo(civicMap);
    layer.bindTooltip(`#${m.id} · ${escapeHtml(m.title)}`,{direction:'top',offset:[0,-8],opacity:.95});
    layer.bindPopup(`<div class="civic-popup"><b>#${m.id} · ${escapeHtml(m.title)}</b><span>${escapeHtml(m.ward)}, ${escapeHtml(m.village)}</span><span>${escapeHtml(m.departmentLabel)}</span><span>Status: <strong>${escapeHtml(m.status)}</strong></span><span>Priority: <strong>${Number(m.priority||0)}/100</strong></span>${isEscalated?'<span class="popup-alert">SLA Escalated</span>':''}<a href="/complaint/${m.id}">Open complaint →</a></div>`);
    civicLayers.push(layer);
  });
  focusMapToMarkers(markers);
  renderAdminLiveLocationMarker(false);
  setTimeout(()=>civicMap?.invalidateSize({pan:false}),100);
}

function resetMapView(){
  const dept=document.getElementById('mapDepartmentFilter');
  const status=document.getElementById('mapStatusFilter');
  if(dept) dept.value='all';
  if(status) status.value='all';
  if(civicMapMode==='fallback') renderFallbackMap('Offline-safe map view');
  else applyMapFilters();
}

async function loadCommandCenter(){
  try{
    const res=await fetch('/api/dashboard-data',{headers:{'Accept':'application/json'},cache:'no-store'});
    if(!res.ok) throw new Error(`Dashboard API returned ${res.status}`);
    const data=await res.json();
    renderMap(data.markers||[]);
    drawChart('deptPerformanceChart','bar',(data.departmentPerformance||[]).map(d=>d.label),(data.departmentPerformance||[]).map(d=>d.rate),'Resolution %');
    drawChart('wardChart','bar',(data.wardAnalytics||[]).map(w=>w.ward),(data.wardAnalytics||[]).map(w=>w.rate),'Resolution %');
    drawChart('workerChart','bar',(data.workers||[]).map(w=>w.id),(data.workers||[]).map(w=>w.active),'Active tasks');
  }catch(err){
    console.error(err);
    civicMarkers=[];
    const map=document.getElementById('adminMap');
    if(map) map.innerHTML='<div class="fallback-map empty"><b>Dashboard data could not be loaded.</b><span>Refresh the page or restart Flask.</span></div>';
    updateMapCount([]);
    document.querySelectorAll('canvas').forEach(c=>{
      const p=c.parentElement;
      if(p&&!p.querySelector('.chart-error')){
        const e=document.createElement('div'); e.className='chart-error'; e.textContent='Analytics could not be loaded. Refresh the page.'; p.appendChild(e);
      }
    });
  }
}

function setupTaskFilters(){
  document.querySelectorAll('.task-filter').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.querySelectorAll('.task-filter').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      const filter=btn.dataset.taskFilter;
      document.querySelectorAll('.worker-task-card').forEach(card=>{
        const status=card.dataset.taskStatus;
        const priority=Number(card.dataset.taskPriority||0);
        const escalated=card.dataset.taskEscalated==='1';
        let show=true;
        if(filter==='active') show=status!=='Resolved';
        if(filter==='priority') show=status!=='Resolved'&&priority>=70;
        if(filter==='escalated') show=status!=='Resolved'&&escalated;
        if(filter==='resolved') show=status==='Resolved';
        card.hidden=!show;
      });
    });
  });
}

function setupWorkerFilters(){
  document.querySelectorAll('.worker-filter').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.querySelectorAll('.worker-filter').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      const filter=btn.dataset.workerFilter;
      document.querySelectorAll('.worker-directory-card').forEach(card=>{
        card.hidden=filter!=='all'&&card.dataset.workerDepartment!==filter;
      });
    });
  });
}

function setupSidebarNavigation(){
  const sidebar=document.querySelector('.sidebar');
  if(!sidebar) return;
  sidebar.querySelectorAll('a[href^="#"]').forEach(link=>{
    link.addEventListener('click',()=>{
      sidebar.querySelectorAll('a').forEach(a=>a.classList.remove('active'));
      link.classList.add('active');
      if(link.getAttribute('href')==='#map') setTimeout(()=>civicMap?.invalidateSize({pan:false}),350);
    });
  });
}

document.addEventListener('change',e=>{
  if(e.target&&(e.target.id==='mapDepartmentFilter'||e.target.id==='mapStatusFilter')) applyMapFilters();
});

document.addEventListener('DOMContentLoaded',()=>{
  setupTaskFilters();
  setupWorkerFilters();
  setupSidebarNavigation();
  document.querySelectorAll('.flash').forEach(el=>setTimeout(()=>{el.style.opacity='0';el.style.transform='translateY(-8px)';setTimeout(()=>el.remove(),250)},5000));
  window.addEventListener('resize',()=>setTimeout(()=>civicMap?.invalidateSize({pan:false}),120));
});

// ============================================================================
// CivicOS integrated navigation, home map and citizen live-update experience.
// ============================================================================
let homeCivicMap = null;
let complaintPollTimer = null;

function toggleMobileMenu(button){
  const nav = document.getElementById('primaryNav');
  if(!nav) return;
  const open = !nav.classList.contains('open');
  nav.classList.toggle('open', open);
  if(button) button.setAttribute('aria-expanded', String(open));
}

function toggleCivicTheme(){
  const root = document.documentElement;
  const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
  root.dataset.theme = next;
  try{ localStorage.setItem('civicos-theme', next); }catch(_e){}
}

function renderHomeMapFallback(markers, message='Live map tiles unavailable'){
  const el = document.getElementById('homeCivicMap');
  if(!el) return;
  const valid=(markers||[]).filter(m=>validCoordinate(m.lat)&&validCoordinate(m.lon));
  if(!valid.length){
    el.innerHTML='<div class="home-map-empty"><b>No mapped complaints yet.</b><span>GPS-confirmed complaints will appear here.</span></div>';
    return;
  }
  const lats=valid.map(m=>Number(m.lat)), lons=valid.map(m=>Number(m.lon));
  let minLat=Math.min(...lats),maxLat=Math.max(...lats),minLon=Math.min(...lons),maxLon=Math.max(...lons);
  if(minLat===maxLat){minLat-=.02;maxLat+=.02} if(minLon===maxLon){minLon-=.02;maxLon+=.02}
  const dots=valid.slice(0,24).map(m=>{
    const x=6+88*((Number(m.lon)-minLon)/(maxLon-minLon));
    const y=7+82*(1-((Number(m.lat)-minLat)/(maxLat-minLat)));
    const c=m.escalated?'#dc3545':colorForDepartment(m.department);
    return `<a href="/track?cid=${m.id}" class="home-fallback-dot" title="#${m.id} ${escapeHtml(m.title)}" style="left:${x}%;top:${y}%;background:${c}"></a>`;
  }).join('');
  el.innerHTML=`<div class="home-map-fallback"><div class="fallback-map-grid"></div><div class="fallback-road road-a"></div><div class="fallback-road road-b"></div><div class="fallback-road road-c"></div>${dots}<small>${escapeHtml(message)}</small></div>`;
}

async function initHomeCivicMap(){
  const el=document.getElementById('homeCivicMap');
  if(!el) return;
  let markers=[];
  try{
    const res=await fetch('/api/dashboard-data',{headers:{Accept:'application/json'},cache:'no-store'});
    if(!res.ok) throw new Error('dashboard data unavailable');
    const data=await res.json();
    markers=(data.markers||[]).filter(m=>validCoordinate(m.lat)&&validCoordinate(m.lon));
  }catch(err){
    console.error(err);
    renderHomeMapFallback([], 'Civic data unavailable');
    return;
  }
  if(typeof L==='undefined'){
    renderHomeMapFallback(markers,'Offline-safe civic map');
    return;
  }
  try{
    homeCivicMap=L.map('homeCivicMap',{zoomControl:false,scrollWheelZoom:false,dragging:true,attributionControl:false,preferCanvas:true});
    const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,crossOrigin:true});
    let errors=0;
    tiles.on('tileerror',()=>{errors++; if(errors>=8 && homeCivicMap){try{homeCivicMap.remove()}catch(_e){} homeCivicMap=null; renderHomeMapFallback(markers,'Map tiles unavailable · coordinates preserved');}});
    tiles.addTo(homeCivicMap);
    const layers=[];
    markers.slice(0,80).forEach(m=>{
      const color=m.escalated?'#dc3545':colorForDepartment(m.department);
      const marker=L.circleMarker([Number(m.lat),Number(m.lon)],{radius:m.escalated?8:6,color:'#fff',weight:2,fillColor:color,fillOpacity:.95}).addTo(homeCivicMap);
      marker.bindTooltip(`#${m.id} · ${escapeHtml(m.title)}`,{direction:'top'});
      marker.on('click',()=>{window.location.href=`/track?cid=${m.id}`;});
      layers.push(marker);
    });
    if(markers.length===1) homeCivicMap.setView([Number(markers[0].lat),Number(markers[0].lon)],13);
    else if(markers.length>1){
      const bounds=L.latLngBounds(markers.map(m=>[Number(m.lat),Number(m.lon)]));
      homeCivicMap.fitBounds(bounds,{padding:[28,28],maxZoom:11});
    }else homeCivicMap.setView([18.735,75.314],11);
    setTimeout(()=>homeCivicMap?.invalidateSize({pan:false}),250);
  }catch(err){
    console.error(err);
    renderHomeMapFallback(markers,'Offline-safe civic map');
  }
}

async function enableComplaintAlerts(){
  const button=document.getElementById('enableComplaintAlerts');
  if(!('Notification' in window)){
    if(button) button.textContent='Browser alerts are not supported here';
    return;
  }
  try{
    const permission=await Notification.requestPermission();
    if(permission==='granted'){
      try{localStorage.setItem('civicos-browser-alerts','1')}catch(_e){}
      if(button){button.textContent='✓ Browser alerts enabled';button.disabled=true;}
      new Notification('CivicOS alerts enabled',{body:'You will be notified when this open tracking page receives a new complaint update.'});
    }else if(button){
      button.textContent='Alerts permission not enabled';
    }
  }catch(_e){
    if(button) button.textContent='Could not enable browser alerts';
  }
}

function setupComplaintLiveUpdates(){
  const strip=document.getElementById('complaintLiveStrip');
  if(!strip) return;
  const cid=strip.dataset.complaintId;
  let lastUpdated=strip.dataset.updatedAt||'';
  let lastNotificationId=Number(strip.dataset.notificationId||0);
  const button=document.getElementById('enableComplaintAlerts');
  try{
    if('Notification' in window && Notification.permission==='granted' && localStorage.getItem('civicos-browser-alerts')==='1'){
      if(button){button.textContent='✓ Browser alerts enabled';button.disabled=true;}
    }
  }catch(_e){}

  const poll=async()=>{
    try{
      const res=await fetch(`/api/complaint/${cid}/state`,{headers:{Accept:'application/json'},cache:'no-store'});
      if(!res.ok) return;
      const data=await res.json();
      const liveText=document.getElementById('liveComplaintText');
      if(data.updatedAt && data.updatedAt!==lastUpdated){
        const notification=data.latestNotification;
        if(notification && Number(notification.id)>lastNotificationId){
          lastNotificationId=Number(notification.id);
          if('Notification' in window && Notification.permission==='granted'){
            try{new Notification(notification.title||`CivicOS complaint #${cid}`,{body:notification.message||`Status: ${data.statusLabel}`});}catch(_e){}
          }
        }
        lastUpdated=data.updatedAt;
        if(liveText) liveText.textContent=`New update received · ${data.statusLabel} · refreshing…`;
        setTimeout(()=>window.location.reload(),1000);
      }else if(liveText){
        liveText.textContent=`Live · ${data.statusLabel} · ${data.worker} · SLA ${data.sla}`;
      }
    }catch(err){
      console.error('CivicOS live update poll failed',err);
    }
  };
  poll();
  clearInterval(complaintPollTimer);
  complaintPollTimer=setInterval(poll,15000);
}

document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('#primaryNav a').forEach(link=>link.addEventListener('click',()=>{
    const nav=document.getElementById('primaryNav');
    const button=document.querySelector('.mobile-menu-toggle');
    if(nav?.classList.contains('open')){
      nav.classList.remove('open');
      button?.setAttribute('aria-expanded','false');
    }
  }));
  document.addEventListener('click',event=>{
    document.querySelectorAll('.nav-dropdown[open],.language-menu[open]').forEach(details=>{
      if(!details.contains(event.target)) details.removeAttribute('open');
    });
  });
});

document.addEventListener('DOMContentLoaded',()=>{
  initAdminLiveLocation();
});
