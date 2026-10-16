from pathlib import Path

html_path = Path("motorpulse/web/index.html")
html = html_path.read_text(encoding="utf-8")
old = '<div class="history-actions"><button type="submit" id="history-apply">Load trends</button><button type="button" id="history-newer" disabled>Newer page</button><button type="button" id="history-older" disabled>Older page</button><button type="button" id="history-latest">Current recording</button></div>'
new = old + '\n<div class="history-actions" role="group" aria-label="Export loaded page as synthetic simulation files"><button type="button" id="history-export-csv" disabled>Export loaded page CSV</button><button type="button" id="history-export-rms" disabled>Download vibration SVG</button><button type="button" id="history-export-temp" disabled>Download temperature SVG</button><button type="button" id="history-export-rpm" disabled>Download RPM SVG</button></div>\n<p class="runtime-help">Exports contain only the currently loaded bounded page and are labelled as <strong>synthetic simulation</strong> data. Evaluation JSON/Markdown reports remain separate write-once CLI artifacts.</p>'
if html.count(old) != 1:
    raise SystemExit("history action anchor mismatch")
html_path.write_text(html.replace(old, new, 1), encoding="utf-8")

js_path = Path("motorpulse/web/history.js")
js = js_path.read_text(encoding="utf-8")
replacements = [
    (
        "  const latest = $('history-latest');\n  const table = $('history-table');",
        "  const latest = $('history-latest');\n  const exportCsvButton = $('history-export-csv');\n  const exportRms = $('history-export-rms');\n  const exportTemp = $('history-export-temp');\n  const exportRpm = $('history-export-rpm');\n  const exportButtons = [exportCsvButton, exportRms, exportTemp, exportRpm];\n  const table = $('history-table');",
        "element",
    ),
    (
        "  let currentPage = null;\n  let token = 0;",
        "  let currentPage = null;\n  let currentRows = [];\n  let token = 0;",
        "state",
    ),
    (
        "  function render(rows, page) {\n    for(const metric of metrics) draw(metric, rows);",
        "  function render(rows, page) {\n    currentRows = rows;\n    for(const metric of metrics) draw(metric, rows);",
        "render",
    ),
    (
        "    const count = rows.length;\n    const badVibration = rows.filter(row => row.event.sensor_quality !== 'good').length;",
        "    const count = rows.length;\n    setExportReady(count > 0);\n    const badVibration = rows.filter(row => row.event.sensor_quality !== 'good').length;",
        "render count",
    ),
    (
        "        currentPage=null;\n        for(const metric of metrics) draw(metric,[]);",
        "        currentPage=null;\n        currentRows = [];\n        setExportReady(false);\n        for(const metric of metrics) draw(metric,[]);",
        "load error",
    ),
    (
        "        resetPage();\n        for(const metric of metrics) draw(metric,[]);\n        buildTable([]);\n        pageLabel.textContent='';\n        setMessage('No recordings yet. Start the simulator with --database.',false);",
        "        resetPage();\n        currentRows = [];\n        setExportReady(false);\n        for(const metric of metrics) draw(metric,[]);\n        buildTable([]);\n        pageLabel.textContent='';\n        setMessage('No recordings yet. Start the simulator with --database.',false);",
        "empty history",
    ),
    (
        "      knownSessions=[];\n      resetPage();\n      for(const metric of metrics) draw(metric,[]);",
        "      knownSessions=[];\n      resetPage();\n      currentRows = [];\n      setExportReady(false);\n      for(const metric of metrics) draw(metric,[]);",
        "session error",
    ),
]
for old_text, new_text, label in replacements:
    if js.count(old_text) != 1:
        raise SystemExit(f"{label} anchor mismatch")
    js = js.replace(old_text, new_text, 1)

function_anchor = "  function appendOption(select, value, text) {"
functions = r'''  function setExportReady(ready) {
    for (const button of exportButtons) button.disabled = !ready;
  }
  function csvCell(value) {
    let text = value === null || value === undefined ? '' : String(value);
    if (/^[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  }
  function exportName(suffix) {
    const safe = value => String(value || 'unknown').replace(/[^A-Za-z0-9._-]+/g, '-').slice(0, 80) || 'unknown';
    return 'motorpulse-synthetic-history-' + safe(sessions.value) + '-' + safe(assets.value) +
      '-page-' + (position + 1) + suffix;
  }
  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }
  function exportCsv() {
    if (!currentRows.length) return;
    const lines = [
      ['MotorPulse AI synthetic simulation export'],
      ['session_id', sessions.value],
      ['asset_id', assets.value],
      ['page', String(position + 1)],
      [],
      ['timestamp_utc','rms_g','temperature_c','rpm','sensor_quality','health'],
    ];
    for (const row of currentRows) {
      const event = row.event || {};
      lines.push([
        event.timestamp_utc,
        event.rms_g,
        event.temperature_c,
        event.rpm,
        event.sensor_quality,
        event.health,
      ]);
    }
    const csv = lines.map(values => values.map(csvCell).join(',')).join('\r\n') + '\r\n';
    downloadBlob(new Blob([csv], {type:'text/csv;charset=utf-8'}), exportName('.csv'));
  }
  function exportSvg(metric) {
    if (!currentRows.length) return;
    const source = $(metric.element);
    const clone = source.cloneNode(true);
    clone.setAttribute('xmlns', NS);
    clone.setAttribute('width', '600');
    clone.setAttribute('height', '200');
    clone.insertBefore(node('title', {}, 'Synthetic simulation chart — ' + metric.label), clone.firstChild);
    const markup = new XMLSerializer().serializeToString(clone);
    downloadBlob(new Blob([markup], {type:'image/svg+xml;charset=utf-8'}),
      exportName('-' + metric.key.replaceAll('_','-') + '.svg'));
  }
'''
if js.count(function_anchor) != 1:
    raise SystemExit("function anchor mismatch")
js = js.replace(function_anchor, functions + function_anchor, 1)

listener_anchor = "  latest.addEventListener('click',async()=>{"
listeners = "  exportCsvButton.addEventListener('click',exportCsv);\n  exportRms.addEventListener('click',()=>exportSvg(metrics[0]));\n  exportTemp.addEventListener('click',()=>exportSvg(metrics[1]));\n  exportRpm.addEventListener('click',()=>exportSvg(metrics[2]));\n  setExportReady(false);\n"
if js.count(listener_anchor) != 1:
    raise SystemExit("listener anchor mismatch")
js = js.replace(listener_anchor, listeners + listener_anchor, 1)
js_path.write_text(js, encoding="utf-8")
