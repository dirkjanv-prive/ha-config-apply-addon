#!/usr/bin/env python3
"""HA Config Apply add-on.

Reacts to Home Assistant button presses:
  - apply button    -> pull main, apply changed dashboards/automations, verify
  - export-to-main  -> export live HA into desired/, commit + push straight to main
  - export-to-branch-> export, commit to a new drift/<ts> branch, open a PR

Talks to Home Assistant through the Supervisor proxy (no HA token). Uses a
GitHub token for git; apply needs only read, export needs read-write on the repo.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
import urllib.error

import websocket  # websocket-client

OPTIONS = json.loads(pathlib.Path("/data/options.json").read_text())
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
if not SUPERVISOR_TOKEN:
    print("[config_apply] FATAL: no SUPERVISOR_TOKEN in environment. "
          "The add-on needs 'hassio_api: true' in config.yaml.", flush=True)
    raise SystemExit(1)

CORE_BASE = "http://supervisor/core"
CORE_WS = "ws://supervisor/core/websocket"
GH_API = "https://api.github.com"

REPO = OPTIONS["github_repo"]
REF = OPTIONS.get("github_ref", "main")
GH_TOKEN = OPTIONS.get("github_token", "").strip()
STATUS = OPTIONS.get("status_entity", "").strip()
SCOPE = OPTIONS.get("apply_scope", "changed")
GIT_NAME = OPTIONS.get("git_name", "HA Config Apply").strip() or "HA Config Apply"
GIT_EMAIL = (OPTIONS.get("git_email", "").strip()
             or "ha-config-apply@users.noreply.github.com")

APPLY_BUTTON = OPTIONS["button_entity"]
EXPORT_MAIN_BUTTON = OPTIONS.get("export_main_button", "").strip()
EXPORT_BRANCH_BUTTON = OPTIONS.get("export_branch_button", "").strip()

REPO_DIR = pathlib.Path("/data/repo")
SHA_FILE = pathlib.Path("/data/last_sha")

APPLY_ENV = {
    **os.environ,
    "HA_URL": CORE_BASE,
    "HA_TOKEN": SUPERVISOR_TOKEN,
    "HA_WS_URL": CORE_WS,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}


def log(msg: str) -> None:
    print(f"[config_apply] {msg}", flush=True)


# ---- HA REST via Supervisor proxy ------------------------------------------
def core_rest(path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{CORE_BASE}/api{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                 "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req).read().decode() or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')}")


def set_status(msg: str) -> None:
    log(f"status: {msg}")
    if not STATUS:
        return
    value = msg[:250]
    try:
        if STATUS.split(".", 1)[0] == "input_text":
            core_rest("/services/input_text/set_value", "POST",
                      {"entity_id": STATUS, "value": value})
        else:
            core_rest(f"/states/{STATUS}", "POST", {"state": value})
    except Exception as e:
        log(f"could not write status entity: {e}")


# ---- git -------------------------------------------------------------------
def repo_url() -> str:
    if GH_TOKEN:
        return f"https://x-access-token:{GH_TOKEN}@github.com/{REPO}.git"
    return f"https://github.com/{REPO}.git"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def ensure_clone() -> None:
    if not (REPO_DIR / ".git").exists():
        REPO_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--branch", REF, repo_url(), str(REPO_DIR)],
                       check=True)
    else:
        git("remote", "set-url", "origin", repo_url())
    # commit identity for export
    git("config", "user.name", GIT_NAME)
    git("config", "user.email", GIT_EMAIL)


def clean_main() -> str:
    """Reset the working tree to the tip of origin/REF and return the sha."""
    git("fetch", "origin", REF)
    git("checkout", "-B", REF, f"origin/{REF}")
    return git("rev-parse", "HEAD")


def has_changes() -> bool:
    return bool(git("status", "--porcelain"))


def gh_open_pr(head: str, title: str, body: str) -> str:
    data = json.dumps({"title": title, "head": head, "base": REF, "body": body}).encode()
    req = urllib.request.Request(
        f"{GH_API}/repos/{REPO}/pulls", data=data, method="POST",
        headers={"Authorization": f"Bearer {GH_TOKEN}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "ha-config-apply"})
    try:
        res = json.loads(urllib.request.urlopen(req).read().decode())
        return f"#{res.get('number')}"
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"PR create -> {e.code}: {e.read().decode(errors='replace')}")


# ---- operations ------------------------------------------------------------
def run_export() -> None:
    cmd = [sys.executable, str(REPO_DIR / "scripts" / "export_ha.py")]
    r = subprocess.run(cmd, cwd=REPO_DIR, env=APPLY_ENV, capture_output=True, text=True)
    log(r.stdout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1])


def do_apply() -> None:
    try:
        set_status(f"Bezig met toepassen... ({time.strftime('%H:%M')})")
        ensure_clone()
        new_sha = clean_main()
        last = SHA_FILE.read_text().strip() if SHA_FILE.exists() else ""
        apply_script = str(REPO_DIR / "scripts" / "apply_ha.py")
        if SCOPE == "changed" and last:
            cmd = [sys.executable, apply_script, "--changed-since", last]
        else:
            cmd = [sys.executable, apply_script, "--all"]
        r = subprocess.run(cmd, cwd=REPO_DIR, env=APPLY_ENV, capture_output=True, text=True)
        log(r.stdout)
        if r.returncode != 0:
            raise RuntimeError((r.stdout or r.stderr).strip().splitlines()[-1])
        v = subprocess.run([sys.executable, apply_script, "--verify"], cwd=REPO_DIR,
                           env=APPLY_ENV, capture_output=True, text=True)
        log(v.stdout)
        if v.returncode != 0:
            raise RuntimeError("apply done, but verify found a mismatch")
        SHA_FILE.write_text(new_sha)
        set_status(f"Toegepast OK - {new_sha[:7]} ({time.strftime('%H:%M')})")
    except Exception as e:
        set_status(f"FOUT (apply): {e} ({time.strftime('%H:%M')})")
        log(f"apply failed: {e}")


def do_export_main() -> None:
    try:
        set_status(f"Bezig met export naar main... ({time.strftime('%H:%M')})")
        ensure_clone()
        clean_main()
        run_export()
        if not has_changes():
            set_status(f"Export: geen wijzigingen ({time.strftime('%H:%M')})")
            return
        git("add", "-A")
        git("commit", "-m", "chore: export live HA state to desired/")
        git("push", "origin", f"HEAD:{REF}")
        sha = git("rev-parse", "HEAD")
        SHA_FILE.write_text(sha)  # avoid re-applying our own export
        set_status(f"Export naar main OK - {sha[:7]} ({time.strftime('%H:%M')})")
    except Exception as e:
        set_status(f"FOUT (export main): {e} ({time.strftime('%H:%M')})")
        log(f"export-main failed: {e}")


def do_export_branch() -> None:
    try:
        set_status(f"Bezig met export naar branch... ({time.strftime('%H:%M')})")
        ensure_clone()
        clean_main()
        run_export()
        if not has_changes():
            set_status(f"Export: geen wijzigingen ({time.strftime('%H:%M')})")
            return
        branch = "drift/" + time.strftime("%Y%m%d-%H%M%S")
        git("checkout", "-b", branch)
        git("add", "-A")
        git("commit", "-m", "chore: export live HA state (drift)")
        git("push", "origin", branch)
        pr = gh_open_pr(branch, "Drift: live HA state export",
                        "Automatische export van de live HA-staat naar `desired/`. "
                        "Review en merge om de wijzigingen vast te leggen.")
        git("checkout", "-B", REF, f"origin/{REF}")  # back to clean main
        set_status(f"Export-PR geopend: {pr} ({time.strftime('%H:%M')})")
    except Exception as e:
        set_status(f"FOUT (export branch): {e} ({time.strftime('%H:%M')})")
        log(f"export-branch failed: {e}")


# ---- button listener -------------------------------------------------------
def listen() -> None:
    handlers = {APPLY_BUTTON: do_apply}
    if EXPORT_MAIN_BUTTON:
        handlers[EXPORT_MAIN_BUTTON] = do_export_main
    if EXPORT_BRANCH_BUTTON:
        handlers[EXPORT_BRANCH_BUTTON] = do_export_branch

    while True:
        ws = None
        try:
            ws = websocket.create_connection(CORE_WS)
            json.loads(ws.recv())  # auth_required
            ws.send(json.dumps({"type": "auth", "access_token": SUPERVISOR_TOKEN}))
            if json.loads(ws.recv()).get("type") != "auth_ok":
                raise RuntimeError("WS auth failed")
            ws.send(json.dumps({"id": 1, "type": "subscribe_events",
                                "event_type": "state_changed"}))
            log(f"listening for presses on: {', '.join(handlers)}")
            set_status(f"Gereed ({time.strftime('%H:%M')})")
            while True:
                msg = json.loads(ws.recv())
                if msg.get("type") != "event":
                    continue
                data = msg.get("event", {}).get("data", {})
                ent = data.get("entity_id")
                if ent in handlers and data.get("new_state"):
                    log(f"button pressed: {ent}")
                    handlers[ent]()
        except Exception as e:
            log(f"listener error: {e}; reconnecting in 10s")
            time.sleep(10)
        finally:
            try:
                if ws:
                    ws.close()
            except Exception:
                pass


if __name__ == "__main__":
    log(f"starting v0.2.0; repo={REPO} ref={REF}")
    listen()
