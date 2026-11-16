"""Loopback-only dashboard for reviewing Android agent proposals."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .android_agent import _load_state, _save_state, set_decision

PAGE = """<!doctype html>
<html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta charset="utf-8"><title>AI Trader - Review</title>
<style>
body{font:16px system-ui;background:#10151d;color:#edf2f7;margin:0;padding:18px}
main{max-width:760px;margin:auto}h1{font-size:24px}.muted{color:#9aa8b8}
.card{background:#1b2532;border:1px solid #344256;border-radius:14px;padding:16px;margin:14px 0}
.row{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
button{padding:12px 16px;border:0;border-radius:9px;font-weight:700;margin:8px 8px 0 0}
.approve{background:#b8f2cf;color:#10251a}.reject{background:#ffc6c6;color:#361010}
.warn{color:#ffd58a;font-size:13px}.price{font-variant-numeric:tabular-nums}
</style><main><h1>AI Trader</h1>
<p class="muted">Android signal review · Manual execution only · No broker connection</p>
<p class="warn">Approval only marks a proposal for manual review. It never places an order.</p>
<div id="items">JavaScript started. Checking proposals…</div>
<script>
(function(){
 var root = document.getElementById('items');
 function esc(value){
  return String(value === null || value === undefined ? '' : value)
   .replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
   });
 }
 function showError(message){root.textContent='Dashboard error: '+message;}
 function load(){
  var request = new XMLHttpRequest();
  request.open('GET','/api/proposals',true);
  request.setRequestHeader('Accept','application/json');
  request.onload = function(){
   if(request.status < 200 || request.status >= 300){
    showError('Proposal endpoint returned HTTP '+request.status); return;
   }
   try{
    var data = JSON.parse(request.responseText);
    if(!data || !Array.isArray(data.proposals)){
     showError('Unexpected response format from /api/proposals'); return;
    }
    if(data.proposals.length === 0){
     root.innerHTML='<p class="muted">No proposals yet. Run the scanner in Termux.</p>'; return;
    }
    var output = '';
    data.proposals.forEach(function(p){
     output += '<section class="card"><div class="row"><strong>'+esc(p.market)+' · '+esc(p.side).toUpperCase()+'</strong><span>'+esc(p.status)+'</span></div>';
     output += '<p class="muted">'+esc(p.timeframe)+' · '+esc(p.signal_bar_time)+'</p>';
     output += '<p>Entry reference: <b class="price">'+esc(p.entry_reference)+'</b></p>';
     output += '<p>Stop loss: <b class="price">'+esc(p.stop_loss)+'</b> · Take profit: <b class="price">'+esc(p.take_profit)+'</b></p>';
     output += '<p>Max planned loss: <b>'+esc(p.max_planned_loss)+' (reference account currency)</b></p>';
     output += '<p class="warn">'+esc(p.data_warning)+'</p><p>'+esc(p.ai && p.ai.summary ? p.ai.summary : '')+'</p>';
     if(p.status === 'pending'){
      output += '<button class="approve" data-id="'+esc(p.id)+'" data-decision="approved_for_manual_review">Approve for manual review</button>';
      output += '<button class="reject" data-id="'+esc(p.id)+'" data-decision="rejected">Reject</button>';
     }
     if(p.status === 'approved_for_manual_review'){
      output += '<p class="warn">Approved for manual review. Verify all values in Exness MT5 and place manually if still valid.</p>';
     }
     output += '</section>';
    });
    root.innerHTML = output;
   }catch(error){showError('Could not parse proposal data: '+error.message);}
  };
  request.onerror = function(){showError('Could not connect to /api/proposals');};
  request.send();
 }
 root.addEventListener('click',function(event){
  var button = event.target;
  if(!button || !button.getAttribute) return;
  var id = button.getAttribute('data-id');
  var decision = button.getAttribute('data-decision');
  if(!id || !decision) return;
  var request = new XMLHttpRequest();
  request.open('POST','/api/decision/'+encodeURIComponent(id),true);
  request.setRequestHeader('Content-Type','application/json');
  request.onload = function(){
   if(request.status < 200 || request.status >= 300){showError('Decision request failed: HTTP '+request.status);return;}
   load();
  };
  request.onerror = function(){showError('Could not submit review decision');};
  request.send(JSON.stringify({decision:decision}));
 });
 load();
 window.setInterval(load,15000);
})();
</script></main></html>"""

def make_handler(state_path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/proposals":
                try:
                    self._json(200, _load_state(state_path))
                except Exception as exc:
                    self._json(500, {"error": str(exc)})
            else:
                self._json(404, {"error": "Not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            prefix = "/api/decision/"
            if not path.startswith(prefix):
                self._json(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4096:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length))
                state = _load_state(state_path)
                proposal = next((p for p in state["proposals"]
                                 if p.get("id") == path[len(prefix):]), None)
                if proposal is None:
                    self._json(404, {"error": "Proposal not found"})
                    return
                set_decision(proposal, payload.get("decision"))
                _save_state(state_path, state)
                self._json(200, {"ok": True, "status": proposal["status"]})
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def log_message(self, fmt, *args):
            return
    return Handler

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="mt5_openai/android_state.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("Security: dashboard must bind to loopback only")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.state))
    print(f"Dashboard: http://127.0.0.1:{args.port}")
    print("Local-only dashboard. Ctrl+C to stop.")
    server.serve_forever()

if __name__ == "__main__":
    main()
