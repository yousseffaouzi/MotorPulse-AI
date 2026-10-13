/* MP-013: Local-only read-only charts of synthetic recorded feature events.
   No CDN/chart dependencies, no physical motor prognostics, no implied RUL. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const form = $('history-filters');
  const sessions = $('history-session');
  const assets = $('history-asset');
  const startInput = $('history-start');
  const endInput = $('history-end');
  const limitInput = $('history-limit');
  const message = $('history-message');
  const pageLabel = $('history-page');
  const older = $('history-older');
  const newer = $('history-newer');
  const apply = $('history-apply');
  const latest = $('history-latest');
  const table = $('history-table');
  const NS = 'http://www.w3.org/2000/svg';
  const MAX_POINTS = 100;
  const UTC = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,6})?(?:Z|[+]00:00)$/;
  const metrics = [
    {key:'rms_g', element:'history-rms', summary:'history-rms-summary', label:'Vibration RMS', unit:'g', digits:3, color:'#5ce0d0', gateQuality:true},
    {key:'temperature_c', element:'history-temp', summary:'history-temp-summary', label:'Temperature', unit:'°C', digits:1, color:'#ffca78', gateQuality:false},
    {key:'rpm', element:'history-rpm', summary:'history-rpm-summary', label:'Motor speed', unit:'RPM', digits:0, color:'#9dbbff', gateQuality:false},
  ];
  let knownSessions = [];
  let cursors = [null];
  let position = 0;
  let currentPage = null;
  let token = 0;
  let busy = false;

  function setMessage(text, isError) {
    message.textContent = text;
    message.classList.toggle('error', !!isError);
  }
  function setBusy(active) {
    busy = active;
    apply.disabled = active;
    latest.disabled = active;
    older.disabled = active || !currentPage || !currentPage.has_more;
    newer.disabled = active || position === 0;
  }
  function appendOption(select, value, text) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = text;
    select.appendChild(option);
  }
  function sessionChoice() {
    return knownSessions.find(s => s.session_id === sessions.value);
  }
  function loadAssetOptions() {
    const previous = assets.value;
    assets.replaceChildren();
    const record = sessionChoice();
    const list = record && record.configuration && Array.isArray(record.configuration.assets)
      ? record.configuration.assets : [];
    for (const row of list) {
      if (typeof row.asset_id === 'string') {
        appendOption(assets, row.asset_id, String(row.name || row.asset_id) + ' (' + row.asset_id + ')');
      }
    }
    if (list.some(row => row.asset_id === previous)) assets.value = previous;
    if (!assets.value && assets.options.length) assets.selectedIndex = 0;
  }
  function utcMicros(text) {
    if (!UTC.test(text)) throw Error('UTC times must be YYYY-MM-DDTHH:MM:SSZ (optional fractional seconds).');
    const head = Date.parse(text.slice(0, 19) + 'Z');
    const fraction = (text.match(/[.]([0-9]{1,6})/) || [,''])[1].padEnd(6, '0');
    if (!Number.isFinite(head)) throw Error('Invalid virtual UTC time.');
    const micros = head * 1000 + Number(fraction);
    if (!Number.isSafeInteger(micros)) throw Error('Time is outside supported chart range.');
    return micros;
  }
  function filters() {
    if (!sessions.value || !assets.value) throw Error('Choose a recorded session and motor.');
    const start = startInput.value.trim();
    const end = endInput.value.trim();
    if (start && end && utcMicros(start) > utcMicros(end)) throw Error('From UTC must be before or equal to To UTC.');
    if (start) utcMicros(start);
    if (end) utcMicros(end);
    const limit = Number(limitInput.value);
    if (!Number.isInteger(limit) || ![25,50,100].includes(limit)) throw Error('Invalid page size.');
    const q = new URLSearchParams({session_id:sessions.value, asset_id:assets.value, limit:String(limit)});
    if (start) q.set('start_utc', start);
    if (end) q.set('end_utc', end);
    if (cursors[position] !== null) q.set('before_id', String(cursors[position]));
    return q;
  }
  function node(name, attributes={}, text=null) {
    const element = document.createElementNS(NS, name);
    for (const [key,value] of Object.entries(attributes)) element.setAttribute(key, String(value));
    if (text !== null) element.textContent = text;
    return element;
  }
  function numeric(event, metric) {
    const value = event[metric.key];
    if (metric.gateQuality && event.sensor_quality !== 'good') return null;
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }
  function draw(metric, rows) {
    const svg = $(metric.element);
    const summary = $(metric.summary);
    const chronological = [...rows].reverse().map(row => row.event);
    const values = chronological.map(event => numeric(event, metric));
    const available = values.filter(value => value !== null);
    const ignored = values.length - available.length;
    svg.replaceChildren(node('title', {}, metric.label + ' over recorded virtual UTC; see accessible numerical table below'));
    svg.setAttribute('aria-label', metric.label + ' over recorded virtual UTC. ' +
      available.length + ' plotted points, ' + ignored + ' unavailable or excluded.');
    if (!values.length || !available.length) {
      svg.appendChild(node('text', {x:20,y:100,fill:'#c3d5ea','font-size':16},
        values.length ? 'No eligible recorded measurements' : 'No recorded measurements for this page'));
      summary.textContent = values.length ? '0 usable points; ' + ignored + ' unavailable/excluded.' : 'No recorded data.';
      return;
    }
    const times = chronological.map(event => utcMicros(event.timestamp_utc));
    const xmin = Math.min(...times), xmax = Math.max(...times);
    const vmin = Math.min(...available), vmax = Math.max(...available);
    const spread = vmax-vmin;
    const pad = spread === 0 ? Math.max(Math.abs(vmin)*0.05, metric.key==='rms_g'?0.01:0.1) : spread*0.1;
    const low = vmin-pad, high = vmax+pad;
    const left=58, right=580, top=12, bottom=165;
    const x = t => xmin===xmax ? (left+right)/2 : left+(t-xmin)/(xmax-xmin)*(right-left);
    const y = v => bottom-(v-low)/(high-low)*(bottom-top);
    for (let i=0;i<=2;i++){
      const yy=top+(bottom-top)*i/2;
      const value=high-(high-low)*i/2;
      svg.appendChild(node('line',{x1:left,y1:yy,x2:right,y2:yy,stroke:'#36516c','stroke-width':1}));
      svg.appendChild(node('text',{x:left-6,y:yy+4,fill:'#bdd1e5','text-anchor':'end','font-size':12},
        value.toFixed(metric.digits)));
    }
    svg.appendChild(node('line',{x1:left,y1:top,x2:left,y2:bottom,stroke:'#9bb0c7'}));
    const lines = [];
    let segment = [];
    const flush = () => {
      if (segment.length > 1) lines.push(node('polyline',{
        points:segment.map(point=>point.join(',')).join(' '),
        stroke:metric.color,'stroke-width':2.8,fill:'none','stroke-linecap':'round','stroke-linejoin':'round'
      }));
      else if(segment.length===1) lines.push(node('circle',{
        cx:segment[0][0],cy:segment[0][1],r:3.2,fill:metric.color
      }));
      segment=[];
    };
    values.forEach((value,i)=>{
      if(value===null) {flush();return;}
      segment.push([x(times[i]).toFixed(3),y(value).toFixed(3)]);
    });
    flush();
    for(const path of lines) svg.appendChild(path);
    const begin=chronological[0].timestamp_utc, end=chronological[chronological.length-1].timestamp_utc;
    svg.appendChild(node('text',{x:left,y:190,fill:'#bdd1e5','font-size':11},begin.slice(5,19)+' UTC'));
    svg.appendChild(node('text',{x:right,y:190,fill:'#bdd1e5','font-size':11,'text-anchor':'end'},end.slice(5,19)+' UTC'));
    summary.textContent = available.length + ' of ' + values.length + ' plotted · ' +
      ignored + ' unavailable/excluded · min ' + vmin.toFixed(metric.digits) + ' ' + metric.unit +
      ' · max ' + vmax.toFixed(metric.digits) + ' ' + metric.unit;
  }
  function buildTable(rows) {
    const fragment = document.createDocumentFragment();
    const columnValues = event => [
      event.timestamp_utc,
      typeof event.rms_g === 'number' && Number.isFinite(event.rms_g) ? event.rms_g.toFixed(3) : 'Unavailable',
      typeof event.temperature_c === 'number' && Number.isFinite(event.temperature_c) ? event.temperature_c.toFixed(1) : 'Unavailable',
      typeof event.rpm === 'number' && Number.isFinite(event.rpm) ? event.rpm.toFixed(0) : 'Unavailable',
      event.sensor_quality || 'unknown',
      event.health || 'unknown',
    ];
    for(const row of rows) {
      const tr = document.createElement('tr');
      for(const value of columnValues(row.event)) {
        const td = document.createElement('td');
        td.textContent = String(value);
        tr.appendChild(td);
      }
      fragment.appendChild(tr);
    }
    table.replaceChildren(fragment);
  }
  function render(rows, page) {
    for(const metric of metrics) draw(metric, rows);
    buildTable(rows);
    currentPage = page;
    const count = rows.length;
    const badVibration = rows.filter(row => row.event.sensor_quality !== 'good').length;
    pageLabel.textContent = 'Page ' + (position+1) + ' · ' + count +
      ' readings (newest first in table) · '+ badVibration +
      ' missing/suspect vibration sensor windows · ' +
      (page.has_more ? 'older readings available' : 'end of filtered history');
    setMessage(count ? 'Showing recorded synthetic features; horizontal axis is virtual UTC, not elapsed wall time. ' +
      'Vibration gaps are intentionally not interpolated.' : 'No recorded measurements match these filters.', false);
  }
  async function loadPage() {
    const request = ++token;
    let params;
    try {params = filters();} catch(error) {
      setMessage(error.message,true);return false;
    }
    setBusy(true);
    setMessage('Loading bounded local history…',false);
    try {
      const response = await fetch('/api/history/events?' + params.toString(),{cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'History request failed (HTTP ' + response.status + ')');
      if (request!==token) return false;
      if (!data || !Array.isArray(data.items) || data.items.length>MAX_POINTS || !data.page) throw Error('Unexpected history response format');
      render(data.items, data.page);
      return true;
    } catch(error) {
      if(request===token) setMessage('History error: ' + error.message,true);
      return false;
    } finally {
      if(request===token) setBusy(false);
    }
  }
  function resetPage() {position=0;cursors=[null];currentPage=null;}
  function switchTo(sessionId) {
    sessions.value = sessionId;
    loadAssetOptions();
    resetPage();
  }
  async function reloadSessions(options={}) {
    const request=++token;
    setBusy(true);
    setMessage('Checking local recording sessions…',false);
    try {
      const [response,statusResponse]=await Promise.all([
        fetch('/api/history/sessions?limit=100',{cache:'no-store'}),
        fetch('/api/status',{cache:'no-store'}),
      ]);
      const results=await response.json();
      if(response.status===409) throw Error('History is disabled. Restart the localhost simulator with --database PATH.sqlite3 to record trends.');
      if(!response.ok) throw Error(results.error || 'Cannot read local recording sessions');
      const status=statusResponse.ok?await statusResponse.json():{};
      if(request!==token)return;
      if (!Array.isArray(results.items)) throw Error('Unexpected session list');
      knownSessions=results.items;
      const previous=options.preferCurrent ? '' : sessions.value;
      sessions.replaceChildren();
      for(const record of knownSessions){
        const date=String(record.created_at_utc || '').slice(0,19);
        appendOption(sessions,record.session_id,record.reason+' · '+date+
          ' · seed '+record.seed+' · '+record.session_id.slice(0,8));
      }
      const preferred=knownSessions.find(r=>r.session_id===previous) ? previous :
        (knownSessions.find(r=>r.session_id===status.session_id) ? status.session_id :
          (knownSessions[0] ? knownSessions[0].session_id : ''));
      if(preferred) switchTo(preferred);
      if(!knownSessions.length) {
        resetPage();
        for(const metric of metrics) draw(metric,[]);
        buildTable([]);
        pageLabel.textContent='';
        setMessage('No recordings yet. Start the simulator with --database.',false);
        return;
      }
      await loadPage();
      if(knownSessions.length===100 && request<=token) {
        pageLabel.textContent+=' · Session selector shows the latest 100 sessions';
      }
    } catch(error){
      if(request!==token)return;
      sessions.replaceChildren();
      assets.replaceChildren();
      knownSessions=[];
      resetPage();
      for(const metric of metrics) draw(metric,[]);
      buildTable([]);
      pageLabel.textContent='';
      setMessage(error.message,true);
    } finally {if(request===token)setBusy(false);}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(busy)return;
    resetPage();
    await loadPage();
  });
  sessions.addEventListener('change',()=>{if(busy)return;loadAssetOptions();resetPage();void loadPage();});
  assets.addEventListener('change',()=>{if(busy)return;resetPage();void loadPage();});
  older.addEventListener('click',async()=>{
    if(busy || !currentPage || !currentPage.has_more)return;
    const old=position;
    cursors.push(currentPage.next_before_id);
    position++;
    if(!await loadPage()) {position=old;cursors.pop();setBusy(false);}
  });
  newer.addEventListener('click',async()=>{
    if(busy || position===0)return;
    const old=position;
    position--;
    if(!await loadPage()) {position=old;setBusy(false);}
  });
  latest.addEventListener('click',async()=>{
    if(busy)return;
    startInput.value='';endInput.value='';
    await reloadSessions({preferCurrent:true});
  });
  window.MotorPulseHistory = {reloadSessions,refresh:()=>{
    if(!knownSessions.length)return Promise.resolve();
    resetPage();
    return loadPage();
  }};
  void reloadSessions({preferCurrent:true});
})();