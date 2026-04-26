"""
Shared .env resolver for the ootb-proposal-automation plugin.

Drop a copy of this file into each skill's `scripts/` directory so any script
can do:

    from _env import resolve_env_file, load_env
    env_path = resolve_env_file()
    load_env(env_path)    # populates os.environ (via python-dotenv)

Search order:
  1. $OOTB_ENV_FILE       (explicit override)
  2. default_env_path()   (user config — where configure-env writes)
         macOS:   ~/Library/Application Support/ootb-proposal-automation/.env
         Linux:   $XDG_CONFIG_HOME/ootb-proposal-automation/.env (or ~/.config)
         Windows: %APPDATA%/ootb-proposal-automation/.env
  3. $CLAUDE_PLUGIN_ROOT/skills/proposal-supabase-sync/scripts/.env (legacy)
  4. script-sibling ./.env (dev fallback — before plugin install)
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


APP_SLUG = "ootb-proposal-automation"


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


def _candidates(caller_script: Path | None) -> list[Path]:
    cands: list[Path] = []

    # 1. explicit override
    override = os.environ.get("OOTB_ENV_FILE")
    if override:
        cands.append(Path(override).expanduser())

    # 2. user config area
    cands.append(default_env_path())

    # 3. plugin install location (legacy / for users still using old layout)
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        cands.append(Path(plugin_root) / "skills" / "proposal-supabase-sync"
                     / "scripts" / ".env")

    # 4. dev fallbacks — near the calling script
    if caller_script is not None:
        here = caller_script.resolve().parent
        cands.append(here / ".env")
        # sibling skill's scripts/.env
        cands.append(here.parent.parent / "proposal-supabase-sync" / "scripts" / ".env")

    return cands


def resolve_env_file(caller_script: Path | None = None) -> Path | None:
    """Return the first existing .env in the search chain, or None."""
    for c in _candidates(caller_script):
        if c.exists() and c.is_file():
            return c
    return None


def load_env(env_path: Path | None = None, *, caller_script: Path | None = None) -> Path | None:
    """Load env vars via python-dotenv (if available) else minimal fallback.

    Returns the resolved path that was loaded, or None if none found.
    """
    path = env_path or resolve_env_file(caller_script)
    if path is None:
        return None

    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path)
    except Exception:
        # Fallback parser — handles KEY=VALUE lines, ignores comments
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return path


def describe_search_chain(caller_script: Path | None = None) -> str:
    """Human-friendly text about where .env is being looked for."""
    lines = ["Searching for .env in:"]
    for i, c in enumerate(_candidates(caller_script), 1):
        mark = "✓" if c.exists() else "·"
        lines.append(f"  {i}. [{mark}] {c}")
    return "\n".join(lines)


if __name__ == "__main__":
    # CLI helper: `python _env.py` prints resolution diagnostic
    print(describe_search_chain(Path(sys.argv[0])))
    p = resolve_env_file(Path(sys.argv[0]))
    print(f"\nResolved: {p if p else '(none found)'}")
