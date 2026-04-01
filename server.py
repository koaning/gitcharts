"""GitCharts server with regeneration API."""

import json
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

CONFIG_PATH = Path("repos_config.json")
SCRIPT_PATH = Path("git_archaeology.py")

# Track regeneration status
status = {"running": False, "repo": None, "progress": "", "error": None}


def regenerate_repo(repo_name, config, granularity):
    """Run git_archaeology.py for a single repo."""
    cmd = [
        "uv", "run", str(SCRIPT_PATH),
        "--repo", config["url"],
        "--samples", str(config["samples"]),
        "--file-extensions", config["extensions"],
        "--granularity", granularity,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def regenerate_single(repo_name, granularity):
    """Regenerate a single repo in background."""
    global status
    status = {"running": True, "repo": repo_name, "progress": "1/1", "error": None}

    try:
        with open(CONFIG_PATH) as f:
            repos = json.load(f)

        if repo_name not in repos:
            raise RuntimeError(f"Unknown repo: {repo_name}")

        regenerate_repo(repo_name, repos[repo_name], granularity)

        subprocess.run(
            ["uv", "run", "python", "generate_repos_list.py"],
            capture_output=True, text=True,
        )
        status["repo"] = None
    except Exception as e:
        status["error"] = str(e)
    finally:
        status["running"] = False


def regenerate_all(granularity):
    """Regenerate all repos in background."""
    global status
    status = {"running": True, "repo": None, "progress": "", "error": None}

    try:
        with open(CONFIG_PATH) as f:
            repos = json.load(f)

        total = len(repos)
        for i, (name, config) in enumerate(repos.items(), 1):
            status["repo"] = name
            status["progress"] = f"{i}/{total}"
            regenerate_repo(name, config, granularity)

        subprocess.run(
            ["uv", "run", "python", "generate_repos_list.py"],
            capture_output=True, text=True,
        )
        status["progress"] = f"{total}/{total}"
        status["repo"] = None
    except Exception as e:
        status["error"] = str(e)
    finally:
        status["running"] = False


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self._json_response(status)
        elif self.path == "/api/config":
            with open(CONFIG_PATH) as f:
                self._json_response(json.load(f))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/regenerate":
            if status["running"]:
                self._json_response({"error": "Already running"}, code=409)
                return

            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            granularity = body.get("granularity", "Week")
            repo = body.get("repo")

            if repo:
                target = regenerate_single
                args = (repo, granularity)
            else:
                target = regenerate_all
                args = (granularity,)

            thread = threading.Thread(target=target, args=args, daemon=True)
            thread.start()
            self._json_response({"started": True})
        else:
            self.send_error(404)

    def do_PUT(self):
        if self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            with open(CONFIG_PATH, "w") as f:
                json.dump(body, f, indent=2)
                f.write("\n")
            self._json_response({"saved": True})
        else:
            self.send_error(404)

    def _json_response(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Silence request logs


if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    server = HTTPServer((host, port), Handler)
    print(f"GitCharts server running on http://{host}:{port}")
    server.serve_forever()
