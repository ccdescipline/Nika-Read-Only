from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import clone, config, jobs, rdp, virt

UI = Path(__file__).with_name("ui.html")


def _json(handler: BaseHTTPRequestHandler, code: int, payload) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    n = int(handler.headers.get("Content-Length") or 0)
    if n <= 0:
        return {}
    raw = handler.rfile.read(n)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _status() -> dict:
    st = rdp.status()
    return {
        "rdp": st,
        "vms": virt.list_vms(st.get("name") or ""),
        "jobs": jobs.list_jobs()[-8:],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            data = UI.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/status":
            try:
                _json(self, 200, _status())
            except Exception as e:
                _json(self, 500, {"error": str(e)})
            return
        if path.startswith("/api/jobs/"):
            job = jobs.get(path.rsplit("/", 1)[-1])
            if not job:
                _json(self, 404, {"error": "job not found"})
                return
            _json(self, 200, job)
            return
        _json(self, 404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = _read_json(self)
        except json.JSONDecodeError:
            _json(self, 400, {"error": "bad json"})
            return
        name = (body.get("name") or "").strip()
        try:
            if path == "/api/start":
                virt.start(name)
                if rdp.saved_target() == name:
                    rdp.apply(name)
                _json(self, 200, _status())
                return
            if path == "/api/stop":
                virt.shutdown(name)
                _json(self, 200, _status())
                return
            if path == "/api/destroy":
                virt.destroy(name)
                _json(self, 200, _status())
                return
            if path == "/api/rdp":
                info = rdp.switch(name, start_if_down=bool(body.get("start")))
                st = _status()
                st["ok"] = info
                _json(self, 200, st)
                return
            if path == "/api/clone":
                src = (body.get("src") or "").strip()
                dst = (body.get("dst") or "").strip()
                job_id = jobs.submit(
                    "clone",
                    clone.clone,
                    src=src,
                    dst=dst,
                    overlay=bool(body.get("overlay")),
                    start=bool(body.get("start")),
                )
                _json(self, 200, {"job": job_id})
                return
            if path == "/api/rotate":
                result = clone.rotate(name)
                _json(self, 200, result)
                return
            if path == "/api/delete":
                result = clone.delete_vm(
                    name,
                    keep_disk=bool(body.get("keep_disk")),
                    force=bool(body.get("force")),
                )
                st = _status()
                st["ok"] = result
                _json(self, 200, st)
                return
        except (virt.VirtError, rdp.RdpError, clone.CloneError) as e:
            _json(self, 400, {"error": str(e)})
            return
        except Exception as e:
            _json(self, 500, {"error": str(e)})
            return
        _json(self, 404, {"error": "not found"})


def serve(bind: str, port: int) -> None:
    httpd = ThreadingHTTPServer((bind, port), Handler)
    host_ip = config.host_ipv4()
    print(f"vmctl ui  http://{host_ip or bind}:{port}/", flush=True)
    print(f"bind {bind}:{port}", flush=True)
    httpd.serve_forever()
