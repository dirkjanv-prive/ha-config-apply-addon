#!/usr/bin/env python3
"""HA Config Apply add-on.

Listens for a Home Assistant button press and, when pressed, fetches the latest
config from the GitHub repo and applies it via the repo's own apply_ha.py. Talks
to Home Assistant through the Supervisor proxy, so it needs no separate HA token
and Protection mode can stay on. The only secret is a read-only GitHub token.

Flow on each button press:
  1. git fetch + hard reset the config repo to the configured ref
  2. run scripts/apply_ha.py (changed since last applied commit, or --all)
  3. verify live == desired
  4. write a human-readable result back to a status text entity
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

import websocket  # websocket-client

OPTIONS = json.loads(pathlib.Path("/data/options.json").read_text())
SUPERVISOR_TOKEN = os.environ["SUPERVISOR_TOKEN"]

# Supervisor proxy endpoints (no HA token needed).
CORE_BASE = "http://supervisor/core"          # REST: /core/api/...
CORE_WS = "ws://supervisor/core/websocket"

REPO = OPTIONS["github_repo"]
REF = OPTIONS.get("github_ref", "main")
GH_TOKEN = OPTIONS.get("github_token", "").strip()
BUTTON = OPTIONS["button_entity"]
STATUS = OPTIONS.get("status_entity", "").strip()
SCOPE = OPTIONS.get("apply_scope", "changed")

REPO_DIR = pathlib.Path("/data/repo")
SHA_FILE = pathlib.Path("/data/last_sha")

APPLY_ENV = {
    **os.environ,
    "HA_URL": CORE_BASE,            # rest path /api/... -> /core/api/...
    "HA_TOKEN": SUPERVISOR_TOKEN,
    "HA_WS_URL": CORE_WS,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}


def log(msg: str) -> None:
    print(f"[config_apply] {msg}", flush=True)


# ---- HA REST via Supervisor proxy ------------------------------------------
def core_rest(path: str, method: str = "GET", body: dict | None = None):
    import urllib.request
    import urllib.error
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{CORE_BASE}/api{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                 "Content-Type": "application/json"},
    )
    try:
        return json.loads(urllib.request.urlopen(req).read().decode() or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')}")


def set_status(msg: str) -> None:
    """Write a short status string back to HA, if a status entity is configured."""
    log(f"status: {msg}")
    if not STATUS:
        return
    # input_text has a 255-char cap by default.
    value = msg[:250]
    try:
        domain = STATUS.split(".", 1)[0]
        if domain == "input_text":
            core_rest("/services/input_text/set_value", "POST",
                      {"entity_id": STATUS, "value": value})
        else:
            # Fallback: set the state directly (works for a template/sensor helper).
            core_rest(f"/states/{STATUS}", "POST", {"state": value})
    except Exception as e:
        log(f"could not write status entity: {e}")


# ---- git ------------------------------------------------------------------
def repo_url() -> str:
    if GH_TOKEN:
        return f"https://x-access-token:{GH_TOKEN}@github.com/{REPO}.git"
    return f"https://github.com/{REPO}.git"


def git(*args: str, cwd: pathlib.Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def sync_repo() -> str:
    """Clone or update the repo to the tip of REF. Returns the new HEAD sha."""
    if not (REPO_DIR / ".git").exists():
        REPO_DIR.mkdir(parents=True, exist_ok=True)
        git("clone", "--branch", REF, "--depth", "50", repo_url(), str(REPO_DIR))
    else:
        # refresh the auth'd remote in case the token changed
        git("remote", "set-url", "origin", repo_url(), cwd=REPO_DIR)
        git("fetch", "origin", REF, cwd=REPO_DIR)
        git("reset", "--hard", f"origin/{REF}", cwd=REPO_DIR)
    return git("rev-parse", "HEAD", cwd=REPO_DIR)


# ---- apply ----------------------------------------------------------------
def run_apply(new_sha: str) -> None:
    last = SHA_FILE.read_text().strip() if SHA_FILE.exists() else ""
    apply_script = str(REPO_DIR / "scripts" / "apply_ha.py")

    if SCOPE == "changed" and last:
        cmd = [sys.executable, apply_script, "--changed-since", last]
    else:
        cmd = [sys.executable, apply_script, "--all"]

    log(f"applying: {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, cwd=REPO_DIR, env=APPLY_ENV,
                       capture_output=True, text=True)
    log(r.stdout)
    if r.stderr:
        log(r.stderr)
    if r.returncode != 0:
        raise RuntimeError(r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr.strip())

    # verify
    v = subprocess.run([sys.executable, apply_script, "--verify"], cwd=REPO_DIR,
                       env=APPLY_ENV, capture_output=True, text=True)
    log(v.stdout)
    if v.returncode != 0:
        raise RuntimeError("apply done, but verify found a mismatch")

    SHA_FILE.write_text(new_sha)


def do_apply() -> None:
    ts = time.strftime("%H:%M")
    try:
        set_status(f"Bezig met toepassen... ({ts})")
        new_sha = sync_repo()
        run_apply(new_sha)
        set_status(f"Toegepast OK - {new_sha[:7]} ({time.strftime('%H:%M')})")
    except Exception as e:
        set_status(f"FOUT: {e} ({time.strftime('%H:%M')})")
        log(f"apply failed: {e}")


# ---- button listener (HA WebSocket via Supervisor proxy) -------------------
def listen() -> None:
    while True:
        try:
            ws = websocket.create_connection(CORE_WS)
            json.loads(ws.recv())  # auth_required
            ws.send(json.dumps({"type": "auth", "access_token": SUPERVISOR_TOKEN}))
            if json.loads(ws.recv()).get("type") != "auth_ok":
                raise RuntimeError("WS auth failed")
            ws.send(json.dumps({"id": 1, "type": "subscribe_events",
                                "event_type": "state_changed"}))
            log(f"listening for presses on {BUTTON}")
            set_status(f"Gereed ({time.strftime('%H:%M')})")
            while True:
                msg = json.loads(ws.recv())
                if msg.get("type") != "event":
                    continue
                data = msg.get("event", {}).get("data", {})
                if data.get("entity_id") != BUTTON:
                    continue
                # input_button press => new_state.state changes to a fresh timestamp
                if data.get("new_state"):
                    log("button pressed -> applying")
                    do_apply()
        except Exception as e:
            log(f"listener error: {e}; reconnecting in 10s")
            time.sleep(10)
        finally:
            try:
                ws.close()
            except Exception:
                pass


if __name__ == "__main__":
    log(f"starting; repo={REPO} ref={REF} button={BUTTON} scope={SCOPE}")
    listen()
