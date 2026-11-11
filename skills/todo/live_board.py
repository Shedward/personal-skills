# /// script
# requires-python = ">=3.9"
# dependencies = ["watchfiles==1.1.1"]
# ///
"""Serve a live local todo or portfolio board."""
import argparse
from contextlib import suppress
from html import escape
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import shutil
import sys
from threading import Condition, Event, Lock, Thread
from time import time_ns
from urllib.parse import parse_qs, urlsplit

SKILLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILLS))
from portfolio import board as portfolio, collect
from todo import board as todo
import todo_render as ui


class LiveBoard:
    def __init__(self, root, snapshot=None, group=None, current=None, opened=None, prs=None):
        self.root, self.snapshot, self.prs = root, snapshot, prs
        self.group, self.current, self.opened = group, current, opened
        self.views, self.assets = {}, {}
        self.lock = Lock()
        self.changed, self.stop = Condition(), Event()
        self.version = time_ns()
        self.watched_files = {p for p in (snapshot, prs) if p}

    def observe(self):
        from watchfiles import watch

        directories = {self.root, *(p.parent for p in self.watched_files)}
        def relevant(change, filename):
            path = Path(filename)
            return path in self.watched_files or path.is_relative_to(self.root)
        try:
            first = True
            for changes in watch(*directories, watch_filter=relevant, stop_event=self.stop, debounce=180, step=45,
                                 yield_on_timeout=True, rust_timeout=1000):
                if not first and not changes:
                    continue
                first = False
                with self.changed:
                    self.version += 1
                    self.changed.notify_all()
        except OSError as error:
            print(f"Ошибка наблюдения за доской: {error}", file=sys.stderr, flush=True)

    def page(self):
        with self.lock:
            version = self.version
            views = {}
            if self.snapshot:
                snapshot, branch_key = collect.board_snapshot(self.snapshot, self.root, self.prs)
                page = portfolio.render(snapshot, None, branch_key or self.current, branch_key, views)
            else:
                page = todo.render(self.root, None, self.group, views=views)
            self.views = views
            opened = "view-" + self.opened if self.opened else ""
            start = f'<body><div id="live-board" data-version="{version}" data-open="{escape(opened)}">'
            return page.replace("<body>", start, 1).replace(ui.SCRIPT, '</div>' + ui.SCRIPT + '<script src="/live.js"></script>', 1)

    def url(self, path):
        path = path.resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            return ""
        mime = mimetypes.guess_type(path.name)[0] or ""
        if not mime.startswith("image/"):
            return ""
        key = sha256(str(path).encode()).hexdigest()
        self.assets[key] = path
        return f"/asset/{key}?v={path.stat().st_mtime_ns}"

    def detail(self, key):
        with self.lock:
            record = self.views.get(key)
            if record is None:
                return None
            if key.startswith("issue-"):
                return portfolio.issue_dialog(record)
            path = (self.root / record["path"]).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                return None
            return ui.view({**record, "body": ui.card_body(path, self)})


class Handler(BaseHTTPRequestHandler):
    def events(self, query):
        board = self.server.board
        seen = self.headers.get("Last-Event-ID") or query.get("since", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b": connected\n\n")
        self.wfile.flush()
        while not board.stop.is_set():
            with board.changed:
                board.changed.wait_for(lambda: seen != str(board.version) or board.stop.is_set(), timeout=10)
                version = str(board.version)
            if seen == version:
                event = ": heartbeat\n\n"
            else:
                seen = version
                event = f"id: {version}\ndata: {version}\n\n"
            self.wfile.write(event.encode())
            self.wfile.flush()

    def send_data(self, data, mime):
        data = data.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(403)
            return
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        board = self.server.board
        try:
            if url.path in ("/", "/board.html"):
                self.send_data(board.page(), "text/html")
            elif url.path == "/live.js":
                self.send_data(Path(__file__).with_name("live_board.js").read_text(encoding="utf-8"), "text/javascript")
            elif url.path == "/events":
                self.events(query)
            elif url.path == "/detail":
                detail = board.detail(query.get("id", [""])[0])
                if detail is None:
                    self.send_error(404)
                else:
                    self.send_data(detail, "text/html")
            elif url.path.startswith("/asset/"):
                path = board.assets.get(url.path[7:])
                if not path or not path.resolve().is_relative_to(board.root) or not path.is_file():
                    self.send_error(404)
                    return
                with path.open("rb") as image:
                    self.send_response(200)
                    self.send_header("Content-Type", mimetypes.guess_type(path.name)[0])
                    self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; style-src 'unsafe-inline'")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    shutil.copyfileobj(image, self.wfile)
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(f"Данные доски недоступны: {error}", file=sys.stderr, flush=True)
            self.send_error(503, "Board data temporarily unavailable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--portfolio", type=Path)
    parser.add_argument("--group")
    parser.add_argument("--current")
    parser.add_argument("--open")
    parser.add_argument("--prs", type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    snapshot = args.portfolio.expanduser().resolve() if args.portfolio else None
    tasks = args.tasks
    if snapshot and not tasks:
        tasks = json.loads(snapshot.read_text(encoding="utf-8")).get("tasks_root")
    if not tasks or not Path(tasks).expanduser().is_dir():
        parser.error("Укажи существующую папку --tasks или tasks_root в снимке портфеля")
    board = LiveBoard(Path(tasks).expanduser().resolve(), snapshot, args.group, args.current, args.open,
                      args.prs.expanduser().resolve() if args.prs else None)
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.board = board
        observer = Thread(target=board.observe, daemon=True)
        observer.start()
        print(f"http://127.0.0.1:{server.server_port}/board.html", flush=True)
        try:
            with suppress(KeyboardInterrupt):
                server.serve_forever()
        finally:
            board.stop.set()
            with board.changed:
                board.changed.notify_all()
            observer.join(timeout=2)


if __name__ == "__main__":
    main()
