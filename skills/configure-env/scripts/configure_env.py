#!/usr/bin/env python3
"""
configure_env.py — write the plugin's .env to a USER-WRITABLE location.

Interactive mode (default, no args):
    python configure_env.py

Non-interactive / scripted mode:
    python configure_env.py \
      --gemini-key     "AIza..." \
      --supabase-url   "https://<ref>.supabase.co" \
      --supabase-key   "eyJ..." \
      [--bucket proposals] [--validate] [--dry-run] \
      [--target /custom/path/.env]

Default target:
    macOS:   ~/Library/Application Support/ootb-proposal-automation/.env
    Linux:   $XDG_CONFIG_HOME/ootb-proposal-automation/.env (or ~/.config)
    Windows: %APPDATA%/ootb-proposal-automation/.env
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

# ── TUI availability ──────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    _RICH = True
except ImportError:
    _RICH = False

try:
    import questionary
    from questionary import Style as QStyle
    _QUESTIONARY = True
except ImportError:
    _QUESTIONARY = False

_TUI = _RICH and _QUESTIONARY


# ── target path resolution ────────────────────────────────────────────────
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
    if not v:
        return "(미설정)"
    if len(v) <= 8:
        return "●" * len(v)
    return f"{v[:4]}{'●' * (len(v) - 8)}{v[-4:]}  ({len(v)}자)"


# ── HTTP validation ───────────────────────────────────────────────────────
def _http(method: str, url: str, headers: dict, body=None, timeout=20):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except Exception as e:
        raise RuntimeError(f"요청 실패: {e}") from e


def validate_supabase(url: str, key: str) -> tuple[bool, str]:
    url = url.rstrip("/")
    try:
        status, _ = _http("GET", f"{url}/rest/v1/rpc/__none__",
                          {"apikey": key, "Authorization": f"Bearer {key}"})
        if status == 404:
            return True,  "연결 성공 (404는 정상 — probe RPC 없음)"
        if status == 401:
            return False, "401 — API 키 인증 실패"
        if status == 200:
            return True,  "200 OK"
        return False, f"예상치 못한 상태 코드: {status}"
    except Exception as e:
        return False, f"오류: {e}"


def validate_gemini(api_key: str, embed_model: str) -> tuple[bool, str]:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models"
           f"/{embed_model}:embedContent?key={api_key}")
    try:
        status, body = _http("POST", url, {"Content-Type": "application/json"},
                             {"content": {"parts": [{"text": "ping"}]}})
        if status == 200:
            return True, "임베딩 API 정상"
        try:
            msg = (json.loads(body or b"{}")
                   .get("error", {}).get("message", body.decode()[:200]))
        except Exception:
            msg = body.decode(errors="replace")[:200]
        return False, f"HTTP {status}: {msg}"
    except Exception as e:
        return False, f"오류: {e}"


# ── .env body ─────────────────────────────────────────────────────────────
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

# ── sanity checks ─────────────────────────────────────────────────────────
def _check_gemini_key(v: str) -> bool | str:
    if not v:
        return "API 키를 입력하세요"
    if not re.match(r"^AIza[0-9A-Za-z_-]{10,}$", v.strip()):
        return "형식이 맞지 않습니다 (AIza... 로 시작해야 합니다)"
    return True


def _check_supabase_url(v: str) -> bool | str:
    if not v:
        return "URL을 입력하세요"
    if not re.match(r"^https://[a-z0-9-]+\.supabase\.co/?$",
                    v.strip().rstrip("/") + "/"):
        return "형식이 맞지 않습니다 (https://<ref>.supabase.co)"
    return True


def _check_supabase_key(v: str) -> bool | str:
    if not v:
        return "Service Role Key를 입력하세요"
    if not v.strip().startswith("eyJ") or len(v.strip()) < 100:
        return "형식이 맞지 않습니다 (eyJ... 로 시작하는 JWT)"
    return True


# ═══════════════════════════════════════════════════════════════════════════
# TUI MODE (rich + questionary)
# ═══════════════════════════════════════════════════════════════════════════
_Q_STYLE = None
if _QUESTIONARY:
    _Q_STYLE = QStyle([
        ("qmark",        "fg:#00BFFF bold"),
        ("question",     "bold"),
        ("answer",       "fg:#00FF9F bold"),
        ("pointer",      "fg:#00BFFF bold"),
        ("highlighted",  "fg:#00BFFF bold"),
        ("selected",     "fg:#00FF9F"),
        ("separator",    "fg:#5C6370"),
        ("instruction",  "fg:#5C6370 italic"),
        ("text",         ""),
        ("disabled",     "fg:#858585 italic"),
    ])


def _read_current_env(target: Path) -> dict[str, str]:
    """기존 .env에서 현재 값을 읽어 반환. 없으면 빈 dict."""
    if not target.exists():
        return {}
    result: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


def _show_current_status(console: "Console", target: Path, current: dict[str, str]) -> None:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                  border_style="bright_black", expand=False)
    table.add_column("키", style="bold", min_width=30)
    table.add_column("현재 값", min_width=40)
    table.add_column("상태", justify="center", min_width=6)

    rows = [
        ("GEMINI_API_KEY",            "필수"),
        ("SUPABASE_URL",              "필수"),
        ("SUPABASE_SERVICE_ROLE_KEY", "필수"),
        ("GEMINI_CHAT_MODEL",         "선택"),
        ("GEMINI_EMBED_MODEL",        "선택"),
        ("EMBED_DIM",                 "선택"),
        ("SUPABASE_BUCKET",           "선택"),
    ]
    for key, req in rows:
        val = current.get(key, "")
        is_sensitive = "KEY" in key or "ROLE" in key
        display = mask(val) if (val and is_sensitive) else (val or "(미설정)")
        if val:
            status = Text("✓", style="bold green")
        else:
            status = Text("✗", style="bold red") if req == "필수" else Text("·", style="dim")
        table.add_row(key, display, status)

    console.print()
    console.print(Panel(table,
                        title="[bold cyan]현재 환경변수 상태[/bold cyan]",
                        border_style="cyan", padding=(0, 1)))
    console.print(f"  저장 위치: [dim]{target}[/dim]")


def _run_validation_tui(console: "Console", values: dict[str, str]) -> bool:
    checks = [
        ("Supabase 연결 확인", lambda: validate_supabase(
            values["SUPABASE_URL"], values["SUPABASE_SERVICE_ROLE_KEY"])),
        ("Gemini API 확인   ", lambda: validate_gemini(
            values["GEMINI_API_KEY"], values["GEMINI_EMBED_MODEL"])),
    ]

    console.print()
    all_ok = True
    with Progress(SpinnerColumn(style="cyan"),
                  TextColumn("[progress.description]{task.description}"),
                  console=console, transient=False) as progress:
        for label, fn in checks:
            task = progress.add_task(f"  {label} ...", total=None)
            ok, msg = fn()
            progress.remove_task(task)
            icon = "[bold green]✓[/bold green]" if ok else "[bold red]✗[/bold red]"
            console.print(f"  {icon}  {label}  [dim]{msg}[/dim]")
            if not ok:
                all_ok = False
    return all_ok


def run_interactive(target: Path, do_validate: bool, dry_run: bool) -> int:
    console = Console()

    # ── 헤더 ─────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        Text("오오티비랩 제안서 자동화\n환경변수 설정 마법사",
             justify="center", style="bold white"),
        subtitle="[dim]Claude Cowork Plugin v0.3[/dim]",
        border_style="bright_blue", padding=(1, 4)
    ))

    # ── 현재 상태 표시 ────────────────────────────────────────────────────
    current = _read_current_env(target)
    _show_current_status(console, target, current)

    if current and any(current.get(k) for k in
                       ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")):
        mode = questionary.select(
            "기존 설정이 있습니다. 어떻게 할까요?",
            choices=[
                questionary.Choice("누락된 키만 채우기", value="patch"),
                questionary.Choice("전체 다시 입력",     value="full"),
                questionary.Choice("취소",               value="cancel"),
            ],
            style=_Q_STYLE,
        ).ask()
        if mode is None or mode == "cancel":
            console.print("\n  [yellow]취소됨.[/yellow]\n")
            return 0
        patch_mode = (mode == "patch")
    else:
        patch_mode = False

    # ── 필수 키 입력 ──────────────────────────────────────────────────────
    console.print()
    console.print(Panel("[bold]필수 키 입력[/bold]\n[dim]비밀번호 필드는 화면에 표시되지 않습니다[/dim]",
                        border_style="bright_blue", padding=(0, 2)))

    def _ask_password(key: str, label: str, hint: str, validator) -> str:
        existing = current.get(key, "")
        if patch_mode and existing:
            console.print(f"  [green]✓[/green] {key}  [dim](기존 값 유지)[/dim]")
            return existing
        console.print(f"\n  [bold cyan]{label}[/bold cyan]")
        console.print(f"  [dim]{hint}[/dim]")
        val = questionary.password(
            "  >", validate=validator, style=_Q_STYLE
        ).ask()
        if val is None:
            raise KeyboardInterrupt
        return val.strip()

    def _ask_text(key: str, label: str, hint: str, default: str) -> str:
        existing = current.get(key, "") or default
        console.print(f"\n  [bold]{label}[/bold]  [dim]{hint}[/dim]")
        val = questionary.text(
            "  >", default=existing, style=_Q_STYLE
        ).ask()
        if val is None:
            raise KeyboardInterrupt
        return val.strip() or default

    try:
        gemini_key = _ask_password(
            "GEMINI_API_KEY",
            "Gemini API Key",
            "Google AI Studio (aistudio.google.com) → API Keys → AIza...",
            _check_gemini_key,
        )
        supabase_url = _ask_text(
            "SUPABASE_URL",
            "Supabase 프로젝트 URL",
            "Settings → API → Project URL  (https://<ref>.supabase.co)",
            "",
        )
        # URL은 텍스트로 받되 검증
        url_check = _check_supabase_url(supabase_url)
        if url_check is not True:
            console.print(f"\n  [red]✗ {url_check}[/red]\n")
            return 1

        supabase_key = _ask_password(
            "SUPABASE_SERVICE_ROLE_KEY",
            "Supabase Service Role Key  ⚠ 관리자 권한 — 절대 공유 금지",
            "Settings → API → service_role  (eyJ... 로 시작하는 JWT)",
            _check_supabase_key,
        )
    except KeyboardInterrupt:
        console.print("\n\n  [yellow]입력 취소됨.[/yellow]\n")
        return 0

    # ── 선택 설정 ─────────────────────────────────────────────────────────
    console.print()
    use_defaults = questionary.confirm(
        "  선택 설정을 기본값으로 사용할까요?\n"
        "  (bucket=proposals  chat=gemini-2.5-flash  embed=gemini-embedding-001  dim=1536)",
        default=True,
        style=_Q_STYLE,
    ).ask()

    if use_defaults:
        bucket      = current.get("SUPABASE_BUCKET",     "proposals")
        chat_model  = current.get("GEMINI_CHAT_MODEL",   "gemini-2.5-flash")
        embed_model = current.get("GEMINI_EMBED_MODEL",  "gemini-embedding-001")
        embed_dim   = current.get("EMBED_DIM",           "1536")
    else:
        console.print()
        try:
            bucket = questionary.text(
                "  Storage 버킷 이름", default=current.get("SUPABASE_BUCKET", "proposals"),
                style=_Q_STYLE).ask() or "proposals"
            chat_model = questionary.text(
                "  Gemini Chat 모델", default=current.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
                style=_Q_STYLE).ask() or "gemini-2.5-flash"
            embed_model = questionary.text(
                "  Gemini Embed 모델", default=current.get("GEMINI_EMBED_MODEL", "gemini-embedding-001"),
                style=_Q_STYLE).ask() or "gemini-embedding-001"
            embed_dim = questionary.text(
                "  임베딩 차원", default=current.get("EMBED_DIM", "1536"),
                style=_Q_STYLE).ask() or "1536"
        except KeyboardInterrupt:
            console.print("\n\n  [yellow]입력 취소됨.[/yellow]\n")
            return 0

    values = {
        "TIMESTAMP":                 time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "GEMINI_API_KEY":            gemini_key,
        "GEMINI_CHAT_MODEL":         chat_model,
        "GEMINI_EMBED_MODEL":        embed_model,
        "EMBED_DIM":                 embed_dim,
        "SUPABASE_URL":              supabase_url.rstrip("/"),
        "SUPABASE_SERVICE_ROLE_KEY": supabase_key,
        "SUPABASE_BUCKET":           bucket,
    }

    # ── 확인 요약 ─────────────────────────────────────────────────────────
    console.print()
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column("키",  style="dim")
    summary.add_column("값")
    for k in ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
              "SUPABASE_BUCKET", "GEMINI_CHAT_MODEL", "GEMINI_EMBED_MODEL", "EMBED_DIM"):
        v = values[k]
        display = mask(v) if "KEY" in k or "ROLE" in k else v
        summary.add_row(k, display)
    console.print(Panel(summary, title="[bold]저장할 내용 확인[/bold]",
                        border_style="yellow", padding=(0, 1)))
    console.print(f"  저장 위치: [bold]{target}[/bold]")

    if dry_run:
        console.print("\n  [yellow](dry-run — 파일 저장 안 함)[/yellow]\n")
        return 0

    ok = questionary.confirm("  위 내용으로 저장할까요?", default=True,
                             style=_Q_STYLE).ask()
    if not ok:
        console.print("\n  [yellow]취소됨.[/yellow]\n")
        return 0

    # ── 검증 ─────────────────────────────────────────────────────────────
    if do_validate:
        console.print()
        console.print(Panel("[bold]키 유효성 검증 중...[/bold]",
                            border_style="bright_blue", padding=(0, 2)))
        all_ok = _run_validation_tui(console, values)
        if not all_ok:
            console.print("\n  [red]✗ 검증 실패 — 키를 확인하고 다시 실행하세요.[/red]\n")
            return 3

    # ── 파일 쓰기 ─────────────────────────────────────────────────────────
    _write_env(target, values)

    # ── 완료 ─────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold green]✅ 환경변수 설정 완료![/bold green]\n\n"
        f"저장 위치: [bold]{target}[/bold]\n\n"
        f"[dim]다음 단계:[/dim]\n"
        f"  [cyan]\"DB 처음 셋업해줘\"[/cyan]   — 스키마 적용\n"
        f"  [cyan]\"이 PDF 등록해줘\"[/cyan]    — 과거 제안서 수집\n"
        f"  [cyan]\"이 RFP로 초안 짜줘\"[/cyan] — 제안서 생성",
        border_style="green", padding=(1, 2)
    ))
    console.print()
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# SHARED: write .env
# ═══════════════════════════════════════════════════════════════════════════
def _write_env(target: Path, values: dict[str, str]) -> None:
    body = ENV_TEMPLATE.format(**values)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        bak = target.with_suffix(f".bak.{int(time.time())}")
        target.rename(bak)
        print(f"기존 .env 백업 → {bak}")
    tmp = target.with_name(".env.new")
    tmp.write_text(body, encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    os.replace(tmp, target)
    print(f"저장 완료: {target}  (mode 600)")


# ═══════════════════════════════════════════════════════════════════════════
# SCRIPTED MODE (non-interactive)
# ═══════════════════════════════════════════════════════════════════════════
def run_scripted(args) -> int:
    # sanity
    if not re.match(r"^AIza[0-9A-Za-z_-]{10,}$", args.gemini_key):
        sys.exit("ERROR: GEMINI_API_KEY must look like an AIza… Google key")
    if not re.match(r"^https://[a-z0-9-]+\.supabase\.co/?$",
                    args.supabase_url.rstrip("/") + "/"):
        sys.exit("ERROR: SUPABASE_URL must be https://<ref>.supabase.co")
    if not args.supabase_key.startswith("eyJ") or len(args.supabase_key) < 100:
        sys.exit("ERROR: SUPABASE_SERVICE_ROLE_KEY does not look like a JWT")
    try:
        int(args.embed_dim)
    except ValueError:
        sys.exit("ERROR: --embed-dim must be integer")

    values = {
        "TIMESTAMP":                 time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "GEMINI_API_KEY":            args.gemini_key,
        "GEMINI_CHAT_MODEL":         args.gemini_chat_model,
        "GEMINI_EMBED_MODEL":        args.gemini_embed_model,
        "EMBED_DIM":                 args.embed_dim,
        "SUPABASE_URL":              args.supabase_url.rstrip("/"),
        "SUPABASE_SERVICE_ROLE_KEY": args.supabase_key,
        "SUPABASE_BUCKET":           args.bucket,
    }

    target = args.target.expanduser() if args.target else default_env_path()
    print(f"target .env: {target}")

    print("\nvalues (masked):")
    for k in ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
              "SUPABASE_BUCKET", "GEMINI_CHAT_MODEL", "GEMINI_EMBED_MODEL", "EMBED_DIM"):
        v = values[k]
        print(f"  {k:<28s} = {mask(v) if 'KEY' in k or 'ROLE' in k else v}")

    if args.dry_run:
        print("\n(dry-run — no file written)")
        return 0

    _write_env(target, values)

    if args.validate:
        print("\nvalidating keys…")
        ok_s, msg_s = validate_supabase(values["SUPABASE_URL"],
                                        values["SUPABASE_SERVICE_ROLE_KEY"])
        print(f"  Supabase: {'✓' if ok_s else '✗'} {msg_s}")
        ok_g, msg_g = validate_gemini(values["GEMINI_API_KEY"],
                                      values["GEMINI_EMBED_MODEL"])
        print(f"  Gemini:   {'✓' if ok_g else '✗'} {msg_g}")
        if not (ok_s and ok_g):
            print("\nvalidation failed — fix the failing key and rerun.",
                  file=sys.stderr)
            return 3

    print("\n✅ done. Consumer scripts will auto-discover this .env.")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(
        description="OOTB 플러그인 환경변수 설정. 인수 없이 실행하면 대화형 TUI 모드.")
    ap.add_argument("--gemini-key")
    ap.add_argument("--supabase-url")
    ap.add_argument("--supabase-key")
    ap.add_argument("--bucket",              default="proposals")
    ap.add_argument("--gemini-chat-model",   default="gemini-2.5-flash")
    ap.add_argument("--gemini-embed-model",  default="gemini-embedding-001")
    ap.add_argument("--embed-dim",           default="1536")
    ap.add_argument("--target",              type=Path, default=None)
    ap.add_argument("--validate",            action="store_true")
    ap.add_argument("--dry-run",             action="store_true")
    ap.add_argument("--no-interactive",      action="store_true",
                    help="강제로 비대화형 모드 (CI/scripted 전용)")
    args = ap.parse_args()

    target = args.target.expanduser() if args.target else default_env_path()
    scripted = args.gemini_key or args.supabase_url or args.supabase_key or args.no_interactive

    if scripted:
        # 기존 CLI 모드 — Claude가 키를 인수로 전달할 때 사용
        if not (args.gemini_key and args.supabase_url and args.supabase_key):
            ap.error("scripted 모드: --gemini-key, --supabase-url, --supabase-key 모두 필요")
        return run_scripted(args)

    # 대화형 TUI 모드
    if not _TUI:
        missing = []
        if not _RICH:
            missing.append("rich")
        if not _QUESTIONARY:
            missing.append("questionary")
        print(f"TUI 의존성 없음 ({', '.join(missing)}). 설치 후 재실행:")
        print(f"  pip install {' '.join(missing)}")
        print("\n또는 비대화형 모드:")
        print("  python configure_env.py --gemini-key AIza... --supabase-url ... --supabase-key eyJ...")
        return 1

    return run_interactive(target, do_validate=True, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
