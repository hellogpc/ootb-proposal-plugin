#!/usr/bin/env python3
"""
configure_env.py — write the plugin's .env to a USER-WRITABLE location.

The plugin itself is installed read-only, so we never write inside
$CLAUDE_PLUGIN_ROOT. Default target:

    macOS:   ~/Library/Application Support/ootb-proposal-automation/.env
    Linux:   $XDG_CONFIG_HOME/ootb-proposal-automation/.env  (or ~/.config)
    Windows: %APPDATA%/ootb-proposal-automation/.env

Consumer scripts (prep.py, prep_rfp.py, embed_query.py, upload_storage.py,
analyze_reference.py) use `_env.resolve_env_file()` which searches:

    1. $OOTB_ENV_FILE (explicit override)
    2. default_env_path() (user config area — where WE write)
    3. $CLAUDE_PLUGIN_ROOT/skills/proposal-supabase-sync/scripts/.env (legacy)
    4. script-sibling ./.env (dev fallback)

Usage (from the configure-env skill):
    configure_env.py \
      --gemini-key     "AIza..." \
      --supabase-url   "https://<ref>.supabase.co" \
      --supabase-key   "eyJ..." \
      [--bucket proposals] [--validate] [--dry-run] \
      [--target /custom/path/.env]     # override default
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


APP_SLUG = "ootb-proposal-automation"


# ── target path resolution ───────────────────────────────────────────────
def default_env_path() -> Path:
    home = Path.home()
    sysname = platform.system()
    if sysname == "Darwin":
        return home / "Library" / "Application Support" / APP_SLUG / ".env"
    if sysname == "Windows":
        appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(appdata) / APP_SLUG / ".env"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(xdg) / APP_SLUG / ".env"


def mask(v: str) -> str:
    if not v: return "(empty)"
    if len(v) <= 8: return "*" * len(v)
    return f"{v[:4]}…{v[-4:]} ({len(v)} chars)"


# ── HTTP validation ──────────────────────────────────────────────────────
def _http(method: str, url: str, headers: dict, body=None, timeout=20):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except Exception as e:
        raise RuntimeError(f"request failed: {e}") from e


def validate_supabase(url: str, key: str) -> tuple[bool, str]:
    url = url.rstrip("/")
    try:
        status, _ = _http("GET", f"{url}/rest/v1/rpc/__none__",
                          {"apikey": key, "Authorization": f"Bearer {key}"})
        if status == 404:  return True,  "reachable (404 for probe rpc is expected)"
        if status == 401:  return False, "401 — apikey rejected"
        if status == 200:  return True,  "200"
        return False, f"unexpected status {status}"
    except Exception as e:
        return False, f"error: {e}"


def validate_gemini(api_key: str, embed_model: str) -> tuple[bool, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{embed_model}:embedContent?key={api_key}"
    try:
        status, body = _http("POST", url, {"Content-Type": "application/json"},
                             {"content": {"parts": [{"text": "ping"}]}})
        if status == 200: return True, "embed OK"
        try:
            msg = json.loads(body or b"{}").get("error", {}).get("message", body.decode()[:200])
        except Exception:
            msg = body.decode(errors="replace")[:200]
        return False, f"HTTP {status}: {msg}"
    except Exception as e:
        return False, f"error: {e}"


# ── .env body ────────────────────────────────────────────────────────────
ENV_TEMPLATE = """\
# Managed by ootb-proposal-automation / configure-env skill.
# Last updated: {TIMESTAMP}

# ── Gemini (always required) ────────────────────────────────────────────
GEMINI_API_KEY={GEMINI_API_KEY}
GEMINI_CHAT_MODEL={GEMINI_CHAT_MODEL}
GEMINI_EMBED_MODEL={GEMINI_EMBED_MODEL}
EMBED_DIM={EMBED_DIM}

# ── Supabase ────────────────────────────────────────────────────────────
SUPABASE_URL={SUPABASE_URL}
SUPABASE_SERVICE_ROLE_KEY={SUPABASE_SERVICE_ROLE_KEY}
SUPABASE_BUCKET={SUPABASE_BUCKET}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini-key", required=True)
    ap.add_argument("--supabase-url", required=True)
    ap.add_argument("--supabase-key", required=True)
    ap.add_argument("--bucket", default="proposals")
    ap.add_argument("--gemini-chat-model",  default="gemini-2.5-flash")
    ap.add_argument("--gemini-embed-model", default="gemini-embedding-001")
    ap.add_argument("--embed-dim", default="1536")
    ap.add_argument("--target", type=Path, default=None,
                    help="override destination path (default: OS-specific user config)")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # sanity
    if not re.match(r"^AIza[0-9A-Za-z_-]{10,}$", args.gemini_key):
        sys.exit("ERROR: GEMINI_API_KEY must look like an AIza… Google key")
    if not re.match(r"^https://[a-z0-9-]+\.supabase\.co/?$", args.supabase_url.rstrip("/") + "/"):
        sys.exit("ERROR: SUPABASE_URL must be https://<ref>.supabase.co")
    if not args.supabase_key.startswith("eyJ") or len(args.supabase_key) < 100:
        sys.exit("ERROR: SUPABASE_SERVICE_ROLE_KEY does not look like a JWT")
    try: int(args.embed_dim)
    except ValueError: sys.exit("ERROR: --embed-dim must be integer")

    values = {
        "TIMESTAMP": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "GEMINI_API_KEY":            args.gemini_key,
        "GEMINI_CHAT_MODEL":         args.gemini_chat_model,
        "GEMINI_EMBED_MODEL":        args.gemini_embed_model,
        "EMBED_DIM":                 args.embed_dim,
        "SUPABASE_URL":              args.supabase_url.rstrip("/"),
        "SUPABASE_SERVICE_ROLE_KEY": args.supabase_key,
        "SUPABASE_BUCKET":           args.bucket,
    }
    body = ENV_TEMPLATE.format(**values)

    target = args.target.expanduser() if args.target else default_env_path()
    print(f"target .env: {target}")
    print(f"OS: {platform.system()}")

    print("\nvalues (masked):")
    for k in ("GEMINI_API_KEY","SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY",
              "SUPABASE_BUCKET","GEMINI_CHAT_MODEL","GEMINI_EMBED_MODEL","EMBED_DIM"):
        v = values[k]
        print(f"  {k:<28s} = { mask(v) if 'KEY' in k else v }")

    if args.dry_run:
        print("\n(dry-run — no file written)")
        return 0

    # mkdir + atomic write + 600
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        bak = target.with_suffix(f".bak.{int(time.time())}")
        target.rename(bak)
        print(f"\nbacked up prior .env → {bak}")

    tmp = target.with_name(".env.new")
    tmp.write_text(body, encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 600 (no-op on Windows)
    except Exception:
        pass
    os.replace(tmp, target)
    print(f"wrote {target} (mode 600)")

    if args.validate:
        print("\nvalidating keys…")
        ok_s, msg_s = validate_supabase(values["SUPABASE_URL"], values["SUPABASE_SERVICE_ROLE_KEY"])
        print(f"  Supabase: {'✓' if ok_s else '✗'} {msg_s}")
        ok_g, msg_g = validate_gemini(values["GEMINI_API_KEY"], values["GEMINI_EMBED_MODEL"])
        print(f"  Gemini:   {'✓' if ok_g else '✗'} {msg_g}")
        if not (ok_s and ok_g):
            print("\nvalidation failed — fix the failing key and rerun.", file=sys.stderr)
            return 3

    print("\n✅ done. Consumer scripts will auto-discover this .env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
