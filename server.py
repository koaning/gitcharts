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


def regenerate_repo(repo_name, config, granularity, branch="", save_as=""):
    """Run git_archaeology.py for a single repo/branch."""
    cmd = [
        "uv", "run", str(SCRIPT_PATH),
        "--repo", config["url"],
        "--samples", str(config["samples"]),
        "--file-extensions", config["extensions"],
        "--granularity", granularity,
    ]
    if branch:
        cmd += ["--branch", branch]
        if save_as and save_as != branch:
            cmd += ["--branch-label", save_as]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def get_develop_branch(config):
    """Find the develop branch (develop, development, dev) for this repo."""
    import re
    result = subprocess.run(
        ["git", "ls-remote", "--heads", config["url"]],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    # Extract branch names from refs/heads/...
    branches = re.findall(r"refs/heads/(\S+)", result.stdout)
    # Priority order: develop > development > dev
    for candidate in ("develop", "development", "dev"):
        if candidate in branches:
            return candidate
    return None


def regenerate_single(repo_name, granularity):
    """Regenerate a single repo (main + develop if exists) in background."""
    global status
    status = {"running": True, "repo": repo_name, "progress": "", "error": None}

    try:
        with open(CONFIG_PATH) as f:
            repos = json.load(f)

        if repo_name not in repos:
            raise RuntimeError(f"Unknown repo: {repo_name}")

        config = repos[repo_name]

        # Main branch
        status["progress"] = "main"
        regenerate_repo(repo_name, config, granularity)

        # Develop branch if exists — always save as "develop" regardless of actual name
        dev_branch = get_develop_branch(config)
        if dev_branch:
            status["progress"] = "develop"
            regenerate_repo(repo_name, config, granularity, branch=dev_branch, save_as="develop")

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
            status["progress"] = f"{i}/{total} main"
            regenerate_repo(name, config, granularity)

            dev_branch = get_develop_branch(config)
            if dev_branch:
                status["progress"] = f"{i}/{total} develop"
                regenerate_repo(name, config, granularity, branch=dev_branch, save_as="develop")

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

    def end_headers(self):
        # Prevent caching of JS/HTML files during development
        if self.path.endswith(('.js', '.html')) or self.path == '/':
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # Silence request logs


if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    server = HTTPServer((host, port), Handler)
    print(f"GitCharts server running on http://{host}:{port}")
    server.serve_forever()
