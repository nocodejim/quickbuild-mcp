"""Create the e2e fixture data on a QuickBuild 16 harness (standard library only).

    python3 -I tests/e2e/qb_fixtures.py --url http://127.0.0.1:18810 --user admin \
        --password ... --server-container <container id> --out .e2e/qbe2e/fixtures.json

1. Configurations root/e2e-sleep (long-running build) and root/e2e-git (git checkout plus 60
   numbered log lines), created through POST /rest/configurations from tests/e2e/fixtures/*.xml
   unless they already exist.
2. A bare Git repository inside the server's data volume (file:// URL, no Git server needed).
3. A baseline build of root/e2e-git, then a new commit by a second author, then a build that
   records that commit as its SCM change. The ids, commit and expectations go to --out (JSON)
   for the e2e tests.

Idempotent: re-running reuses the configurations and repository and records a fresh commit.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = "/opt/quickbuild/data/e2e"
COMMIT_AUTHOR = "Alice Example"
COMMIT_EMAIL = "alice@example.com"
FINISHED = {"SUCCESSFUL", "FAILED", "CANCELLED", "TIMEOUT", "RECOMMENDED"}


class QuickBuild:
    def __init__(self, url: str, user: str, password: str):
        self.url = url.rstrip("/")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def request(self, method: str, path: str, body: bytes | None = None,
                content_type: str | None = None, params: dict | None = None):
        url = f"{self.url}/rest/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = dict(self.headers)
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode()
                return resp.status, (json.loads(text) if text.strip() else None)
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode("utf-8", "replace")

    def configuration_id(self, path: str):
        status, body = self.request("GET", "ids", params={"configuration_path": path})
        return int(body) if status == 200 else None

    def ensure_configuration(self, path: str, xml_file: str) -> int:
        existing = self.configuration_id(path)
        if existing is not None:
            print(f"Configuration {path} exists (id {existing})")
            return existing
        with open(os.path.join(HERE, "fixtures", xml_file), "rb") as handle:
            status, body = self.request("POST", "configurations", handle.read(), "application/xml")
        if status != 200:
            raise SystemExit(f"Creating {path} failed: HTTP {status} {body}")
        print(f"Created configuration {path} (id {body})")
        return int(body)

    def latest_build(self, config_id: int):
        status, body = self.request("GET", f"latest_builds/{config_id}")
        return body if status == 200 and isinstance(body, dict) else None

    def run_build(self, config_id: int, timeout: int = 300) -> dict:
        before = (self.latest_build(config_id) or {}).get("id", 0)
        status, body = self.request(
            "POST", "build_requests",
            json.dumps({"configurationId": config_id, "respectBuildCondition": False}).encode(),
            "application/json",
        )
        if status != 200:
            raise SystemExit(f"Triggering configuration {config_id} failed: HTTP {status} {body}")
        deadline = time.time() + timeout
        while time.time() < deadline:
            build = self.latest_build(config_id)
            if build and build["id"] > before and build.get("status") in FINISHED:
                print(f"Build {build['id']} of configuration {config_id}: {build['status']}")
                if build["status"] != "SUCCESSFUL":
                    raise SystemExit(f"Fixture build {build['id']} ended {build['status']}")
                return build
            time.sleep(2)
        raise SystemExit(f"Build of configuration {config_id} did not finish within {timeout}s")


def in_server(container: str, script: str) -> str:
    result = subprocess.run(
        ["docker", "exec", container, "sh", "-ec", script],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def ensure_repository(container: str) -> None:
    in_server(container, f"""
        if [ ! -d {REPO_DIR}/repo.git ]; then
            mkdir -p {REPO_DIR}
            git init -q --bare -b main {REPO_DIR}/repo.git
            git clone -q {REPO_DIR}/repo.git {REPO_DIR}/work 2>/dev/null
            cd {REPO_DIR}/work
            echo "e2e fixture repository" > README.md
            git add README.md
            git -c user.name="E2E Bot" -c user.email=e2e-bot@example.com commit -q -m "e2e: initial commit"
            git push -q origin HEAD:main
        fi
    """)


def add_commit(container: str) -> dict:
    stamp = time.strftime("%Y%m%d%H%M%S")
    path = f"docs/e2e-{stamp}.txt"
    message = f"e2e: add {path} and touch README"
    sha = in_server(container, f"""
        cd {REPO_DIR}/work
        mkdir -p docs
        echo "{stamp}" > {path}
        echo "{stamp}" >> README.md
        git add -A
        git -c user.name="{COMMIT_AUTHOR}" -c user.email={COMMIT_EMAIL} commit -q -m "{message}"
        git push -q origin HEAD:main
        git rev-parse HEAD
    """)
    return {"sha": sha, "message": message,
            "modifications": [{"action": "MODIFY", "path": "README.md"}, {"action": "ADD", "path": path}]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--server-container", required=True)
    parser.add_argument("--unauthorized-agent-ip", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    qb = QuickBuild(args.url, args.user, args.password)
    sleep_id = qb.ensure_configuration("root/e2e-sleep", "config-sleep.xml")
    git_id = qb.ensure_configuration("root/e2e-git", "config-git.xml")

    ensure_repository(args.server_container)
    baseline = qb.run_build(git_id)
    commit = add_commit(args.server_container)
    changes_build = qb.run_build(git_id)

    fixtures = {
        "sleep_config_id": str(sleep_id),
        "sleep_config_path": "root/e2e-sleep",
        "git_config_id": str(git_id),
        "git_config_path": "root/e2e-git",
        "baseline_build_id": str(baseline["id"]),
        "changes_build_id": str(changes_build["id"]),
        "commit": {**commit, "author": COMMIT_AUTHOR, "repository": "e2e-git"},
        "log_line_prefix": "E2E-LOG-LINE-",
        "log_line_count": 60,
        "unauthorized_agent_ip": args.unauthorized_agent_ip,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(fixtures, handle, indent=2)
    print(f"Fixtures written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
