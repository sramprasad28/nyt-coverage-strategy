import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from app.analytics import build_dashboard
from app.db import connect

STATIC = Path(__file__).resolve().parent / "static"
PORT = 8765
DASHBOARD = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/dashboard":
            self._dashboard()
            return
        if path in ("/", "/index.html"):
            self._file(STATIC / "index.html")
            return
        if path.startswith("/static/"):
            self._file(STATIC / path.removeprefix("/static/"))
            return
        self.send_error(404)

    def _dashboard(self):
        global DASHBOARD
        if DASHBOARD is not None:
            self._json(DASHBOARD)
            return
        connection = connect()
        try:
            DASHBOARD = build_dashboard(connection)
        except Exception as error:
            self._json({"error": str(error)}, status=500)
            return
        finally:
            connection.close()
        self._json(DASHBOARD)

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        root = STATIC.resolve()
        target = path.resolve()
        if not target.is_relative_to(root) or not target.is_file():
            self.send_error(404)
            return
        kind = "text/plain; charset=utf-8"
        if target.suffix == ".html":
            kind = "text/html; charset=utf-8"
        elif target.suffix == ".css":
            kind = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            kind = "text/javascript; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        try:
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)
        except OSError:
            return


def _server(host, family):
    class LocalServer(ThreadingHTTPServer):
        address_family = family
        daemon_threads = True

        def server_bind(self):
            if family == socket.AF_INET6:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            return super().server_bind()

    return LocalServer((host, PORT), Handler)


def main():
    global DASHBOARD
    connection = connect()
    try:
        DASHBOARD = build_dashboard(connection)
        print("dashboard data ready", flush=True)
    except Exception as error:
        print(f"dashboard data failed: {error}", flush=True)
        DASHBOARD = None
    finally:
        connection.close()
    servers = [
        _server("127.0.0.1", socket.AF_INET),
        _server("::1", socket.AF_INET6),
    ]
    print(f"dashboard at http://127.0.0.1:{PORT}", flush=True)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("stopping", flush=True)
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
