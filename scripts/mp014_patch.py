from pathlib import Path

main_path = Path("motorpulse/__main__.py")
main = main_path.read_text(encoding="utf-8")
if main.count("import sqlite3\n") != 1:
    raise SystemExit("sqlite import anchor mismatch")
main = main.replace("import sqlite3\n", "import sqlite3\nimport time\n", 1)

get_anchor = "    def do_GET(self):\n"
sse = '''    def _sse(self) -> None:\n        self.send_response(200)\n        self.send_header("Content-Type", "text/event-stream; charset=utf-8")\n        self.send_header("Cache-Control", "no-store")\n        self.send_header("X-Content-Type-Options", "nosniff")\n        self.end_headers()\n        self.close_connection = True\n        while True:\n            state = self.server.controller.stream_state()\n            payload = json.dumps(\n                state, allow_nan=False, separators=(",", ":")\n            )\n            frame = (\n                "retry: 1500\\n"\n                f"id: {state['snapshot']['tick']}\\n"\n                "event: state\\n"\n                f"data: {payload}\\n\\n"\n            ).encode("utf-8")\n            try:\n                self.wfile.write(frame)\n                self.wfile.flush()\n            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):\n                return\n            time.sleep(1.5)\n\n'''
if main.count(get_anchor) != 1:
    raise SystemExit("GET anchor mismatch")
main = main.replace(get_anchor, sse + get_anchor, 1)

route_old = "        path = target.path\n        if path in ROUTES:\n"
route_new = "        path = target.path\n        if path == \"/api/stream\":\n            self._sse()\n        elif path in ROUTES:\n"
if main.count(route_old) != 1:
    raise SystemExit("GET route anchor mismatch")
main = main.replace(route_old, route_new, 1)
main_path.write_text(main, encoding="utf-8")

html_path = Path("motorpulse/web/index.html")
html = html_path.read_text(encoding="utf-8")
old_pill = '<span class="pill">Auto-refresh: 1.5 s</span>'
new_pill = '<span class="pill" id="live-transport">Live updates: connecting (localhost SSE; polling fallback available)</span>'
if html.count(old_pill) != 1:
    raise SystemExit("transport pill anchor mismatch")
html = html.replace(old_pill, new_pill, 1)

refresh_prefix = "async function refresh(){try{const r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw Error(r.status);const d=await r.json();"
refresh_suffix = "}catch(e){st.textContent='Cannot reach local simulator: '+e.message}}\n"
start = html.find(refresh_prefix)
if start < 0:
    raise SystemExit("refresh prefix mismatch")
body_start = start + len(refresh_prefix)
end = html.find(refresh_suffix, body_start)
if end < 0:
    raise SystemExit("refresh suffix mismatch")
render = html[body_start:end]
replacement = (
    "function applySnapshot(d){" + render + "}\n"
    "async function refresh(){try{const r=await fetch('/api/snapshot',{cache:'no-store'});"
    "if(!r.ok)throw Error(r.status);const d=await r.json();applySnapshot(d)}"
    "catch(e){st.textContent='Cannot reach local simulator: '+e.message}}\n"
)
html = html[:start] + replacement + html[end + len(refresh_suffix):]

mode_anchor = "const mode=document.querySelector('#mode');"
mode_new = "const mode=document.querySelector('#mode');const transport=document.querySelector('#live-transport');"
if html.count(mode_anchor) != 1:
    raise SystemExit("mode anchor mismatch")
html = html.replace(mode_anchor, mode_new, 1)

status_prefix = "async function refreshMode(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Status unavailable');const s=await r.json();"
status_suffix = "}catch(e){mode.textContent='Cannot read simulation status';runtimeActive.textContent='Status unavailable; settings not confirmed';}}\n"
start = html.find(status_prefix)
if start < 0:
    raise SystemExit("status prefix mismatch")
body_start = start + len(status_prefix)
end = html.find(status_suffix, body_start)
if end < 0:
    raise SystemExit("status suffix mismatch")
status_render = html[body_start:end]
replacement = (
    "function applyStatus(s){" + status_render + "}\n"
    "async function refreshMode(){try{const r=await fetch('/api/status',{cache:'no-store'});"
    "if(!r.ok)throw Error('Status unavailable');const s=await r.json();applyStatus(s)}"
    "catch(e){mode.textContent='Cannot read simulation status';runtimeActive.textContent='Status unavailable; settings not confirmed';}}\n"
)
html = html[:start] + replacement + html[end + len(status_suffix):]

startup_old = "loadConfig();\nrefresh();refreshMode();setInterval(()=>{refresh();refreshMode()},1500)\n"
startup_new = """let pollingTimer=null;
function startPollingFallback(){if(pollingTimer!==null)return;refresh();refreshMode();pollingTimer=setInterval(()=>{refresh();refreshMode()},1500);transport.textContent='Live updates: polling fallback (localhost only)';}
function stopPollingFallback(){if(pollingTimer!==null){clearInterval(pollingTimer);pollingTimer=null;}}
function startStreaming(){
  if(!('EventSource' in window)){startPollingFallback();return;}
  transport.textContent='Live updates: connecting (localhost SSE; polling fallback available)';
  const stream=new EventSource('/api/stream');
  stream.addEventListener('state',event=>{
    try{const payload=JSON.parse(event.data);applySnapshot(payload.snapshot);applyStatus(payload.status);stopPollingFallback();transport.textContent='Live updates: localhost SSE';}
    catch(e){startPollingFallback();}
  });
  stream.onerror=()=>{transport.textContent='Live updates: reconnecting; polling fallback active';startPollingFallback();};
}
loadConfig();
startStreaming();
"""
if html.count(startup_old) != 1:
    raise SystemExit("startup polling anchor mismatch")
html = html.replace(startup_old, startup_new, 1)
html_path.write_text(html, encoding="utf-8")
