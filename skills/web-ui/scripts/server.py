#!/usr/bin/env python3
"""
OOTB Proposal Automation — Web UI Server
Usage: python server.py [--port 7979] [--host 127.0.0.1]
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import textwrap
import time
import uuid
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Any

import httpx
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
import uvicorn

# ── paths ──────────────────────────────────────────────────────────────────
HERE        = Path(__file__).parent
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", HERE.parent.parent.parent))
SKILLS      = PLUGIN_ROOT / "skills"

PREP_PY         = SKILLS / "proposal-supabase-sync/scripts/prep.py"
PREP_RFP_PY     = SKILLS / "rfp-to-proposal-pipeline/scripts/prep_rfp.py"
PREPARE_DECK_PY = SKILLS / "ootb-proposal-pptx/scripts/prepare_deck.py"
RENDER_DECK_JS  = SKILLS / "ootb-proposal-pptx/scripts/render_deck.js"

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "ootb-webui"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ── env ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(SKILLS / "configure-env/scripts"))
from _env import load_env as _load_ootb_env  # noqa: E402

_load_ootb_env(caller_script=Path(__file__))

SB_URL    = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
GM_KEY    = os.getenv("GEMINI_API_KEY", "")
GM_CHAT   = os.getenv("GEMINI_CHAT_MODEL",  "gemini-2.5-flash")
GM_EMBED  = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))

# ── task registry ─────────────────────────────────────────────────────────
_logs:   dict[str, list[str]] = {}
_status: dict[str, str]       = {}   # "running" | "done" | "error"
_result: dict[str, dict]      = {}


def _task_start(tid: str) -> None:
    _logs[tid], _status[tid] = [], "running"


def _log(tid: str, msg: str) -> None:
    _logs.setdefault(tid, []).append(msg)


def _task_done(tid: str, payload: dict) -> None:
    _status[tid], _result[tid] = "done", payload


def _task_error(tid: str, msg: str) -> None:
    _log(tid, f"ERROR: {msg}")
    _status[tid] = "error"


# ── Supabase HTTP ─────────────────────────────────────────────────────────
def _sb_headers(extras: dict | None = None) -> dict:
    h = {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
    }
    if extras:
        h.update(extras)
    return h


async def sb_get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{SB_URL}/rest/v1/{path}",
                        headers=_sb_headers(), params=params or {})
        r.raise_for_status()
        return r.json()


async def sb_rpc(fn: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{SB_URL}/rest/v1/rpc/{fn}",
                         headers=_sb_headers(), json=body)
        r.raise_for_status()
        return r.json()


async def sb_upsert(table: str, data: dict) -> Any:
    h = _sb_headers({"Prefer": "resolution=merge-duplicates,return=representation"})
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{SB_URL}/rest/v1/{table}", headers=h, json=data)
        r.raise_for_status()
        return r.json()


async def sb_delete(table: str, row_id: int) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.delete(f"{SB_URL}/rest/v1/{table}?id=eq.{row_id}",
                           headers=_sb_headers())
        r.raise_for_status()


# ── subprocess helper ─────────────────────────────────────────────────────
async def run_proc(tid: str, cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *[str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_buf: list[bytes] = []

    async def drain_stderr() -> None:
        assert proc.stderr
        async for line in proc.stderr:
            _log(tid, line.decode(errors="replace").rstrip())

    async def drain_stdout() -> None:
        assert proc.stdout
        async for chunk in proc.stdout:
            stdout_buf.append(chunk)

    await asyncio.gather(drain_stderr(), drain_stdout())
    await proc.wait()
    return proc.returncode, b"".join(stdout_buf).decode(errors="replace")


# ── Gemini outline synthesis ───────────────────────────────────────────────
_SYNTHESIS_SYSTEM = textwrap.dedent("""
당신은 오오티비랩(OOTB Lab)의 수석 제안PM입니다.
RFP와 유사 사례 제안서를 바탕으로 OOTB 포맷 outline.yaml을 생성하세요.

규칙:
- 슬라이드 타입만 사용: cover, toc, section_divider, hero, content, content_image, closing
- 순서: cover → toc → (section_divider + slides) × 반복 → closing
- content.body: 2~4개 (heading + text)
- TOC items 수 = section_divider 수
- hero 슬라이드 ≤ 2개
- section_divider.number: "01", "02" ... 연속
- 예산/수치는 RFP 명시값만 사용, 없으면 [확인필요]
- 과거 사례 인용 시 (ref: <id>) 표기

YAML만 출력 (마크다운 코드블록 없이). 형식:

brand:
  company_name: "(주)오오티비랩"
project:
  title: "..."
  date: "YYYY년 M월"
slides:
  - type: cover
  - type: toc
    items: ["섹션명1", "섹션명2", "섹션명3", "섹션명4"]
  - type: section_divider
    number: "01"
    title: "..."
  - type: hero
    eyebrow: "[키워드]"
    headline: "핵심 메시지"
    subheadline: "부제"
    highlight: "강조단어"
  - type: content
    breadcrumb: "섹션명 | 소제목"
    title: "슬라이드 제목"
    body:
      - heading: "항목1"
        text: "설명"
      - heading: "항목2"
        text: "설명"
  - type: closing
    message: "감사합니다"
    tagline: "(주)오오티비랩과 함께하겠습니다"
""").strip()


async def synthesize_outline(rfp_meta: dict, rfp_summary: str, proposals: list[dict]) -> str:
    from google import genai
    from google.genai import types

    past = "\n\n".join(
        f"[id={p['id']}] {p.get('title','')} ({p.get('project_year','')}, {p.get('client_name','')})\n"
        f"abstract: {p.get('abstract','')}\n"
        f"key_points: {', '.join(p.get('key_points') or [])}\n"
        f"strategy: {p.get('strategy','')}\n"
        f"deliverables: {', '.join(p.get('deliverables') or [])}"
        for p in proposals
    )
    user_msg = (
        f"=== RFP 정보 ===\n{json.dumps(rfp_meta, ensure_ascii=False, indent=2)}\n\n"
        f"=== RFP 요약 ===\n{rfp_summary}\n\n"
        f"=== 유사 과거 제안서 top-{len(proposals)} ===\n{past or '(없음 — 제로샷 생성)'}"
    )
    client = genai.Client(api_key=GM_KEY)
    resp = client.models.generate_content(
        model=GM_CHAT,
        contents=[{"role": "user",
                   "parts": [{"text": _SYNTHESIS_SYSTEM + "\n\n" + user_msg}]}],
        config=types.GenerateContentConfig(temperature=0.3),
    )
    # Strip accidental markdown fences
    text = resp.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)
        text = re.sub(r"\n```$", "", text.rstrip())
    return text


# ── background task: ingest PDF ───────────────────────────────────────────
async def _ingest_task(tid: str, pdf_path: Path) -> None:
    out_json = DOWNLOAD_DIR / f"{tid}_prep.json"
    try:
        _log(tid, f"📄 파일 수신: {pdf_path.name}")

        rc, _ = await run_proc(tid, [
            sys.executable, PREP_PY,
            str(pdf_path), "--full-json", "-o", str(out_json),
        ])
        if rc != 0:
            _task_error(tid, "prep.py 실패")
            return

        payload = json.loads(out_json.read_text(encoding="utf-8"))
        row: dict = payload["row"]
        embedding: list[float] | None = payload.get("embedding")

        # Format vector for PostgREST
        if embedding:
            row["embedding"] = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"

        _log(tid, "💾 Supabase 저장 중...")
        result = await sb_upsert("proposals", row)
        inserted_id = result[0]["id"] if result else "?"
        _log(tid, f"✅ 등록 완료 — id={inserted_id}, 제목={row.get('title','')}")
        _task_done(tid, {"id": inserted_id, "title": row.get("title", "")})

    except Exception as e:
        _task_error(tid, str(e))
    finally:
        for f in (pdf_path, out_json):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass


# ── background task: generate proposal ────────────────────────────────────
async def _proposal_task(tid: str, rfp_path: Path) -> None:
    tmp_files: list[Path] = [rfp_path]
    try:
        _log(tid, f"📋 RFP 분석 시작: {rfp_path.name}")

        # Step 1 — prep_rfp.py
        rfp_json = DOWNLOAD_DIR / f"{tid}_rfp.json"
        tmp_files.append(rfp_json)
        rc, _ = await run_proc(tid, [
            sys.executable, PREP_RFP_PY, str(rfp_path), "-o", str(rfp_json),
        ])
        if rc != 0:
            _task_error(tid, "RFP 파싱 실패")
            return

        rfp_data      = json.loads(rfp_json.read_text(encoding="utf-8"))
        rfp_meta      = rfp_data["rfp_meta"]
        rfp_summary   = rfp_data.get("rfp_summary", "")
        query_text    = rfp_data.get("query_text", "")
        query_vec     = rfp_data.get("query_embedding", "")

        # Step 2 — hybrid search
        _log(tid, "🔍 유사 제안서 검색 중...")
        search_rows: list[dict] = []
        try:
            search_rows = await sb_rpc("match_proposals", {
                "query_text":      query_text,
                "query_embedding": query_vec,
                "match_count":     3,
            })
        except Exception as e:
            _log(tid, f"⚠ 벡터 검색 실패 ({e}) — 최신 3건으로 대체")
            try:
                search_rows = await sb_get("proposals", {
                    "select": "id,title", "order": "created_at.desc", "limit": "3",
                })
            except Exception:
                search_rows = []

        if not search_rows:
            _log(tid, "⚠ 유사 사례 없음 — 제로샷으로 생성")
            proposals_full: list[dict] = []
        else:
            ids = [str(r["id"]) for r in search_rows]
            _log(tid, f"📚 참고 제안서 id: {', '.join(ids)}")
            proposals_full = await sb_get("proposals", {
                "select": "id,title,client_name,project_year,abstract,key_points,strategy,deliverables",
                "id":     f"in.({','.join(ids)})",
            })

        # Step 3 — synthesize outline.yaml
        _log(tid, "✨ 제안서 구조 합성 중 (Gemini)...")
        outline_yaml = await synthesize_outline(rfp_meta, rfp_summary, proposals_full)

        outline_path = DOWNLOAD_DIR / f"{tid}_outline.yaml"
        tmp_files.append(outline_path)
        outline_path.write_text(outline_yaml, encoding="utf-8")
        _log(tid, "✅ outline.yaml 완료")

        # Step 4 — prepare_deck.py → deck_plan.json
        _log(tid, "🎨 덱 플랜 빌드 중...")
        deck_plan = DOWNLOAD_DIR / f"{tid}_deck_plan.json"
        tmp_files.append(deck_plan)
        rc, _ = await run_proc(tid, [
            sys.executable, PREPARE_DECK_PY, str(outline_path), "-o", str(deck_plan),
        ])
        if rc != 0:
            _task_error(tid, "prepare_deck.py 실패 — outline.yaml 구조를 확인하세요")
            return

        # Step 5 — render_deck.js → .pptx
        _log(tid, "📊 PPT 렌더링 중 (pptxgenjs)...")
        title_safe = re.sub(r"[^\w가-힣]", "_", rfp_meta.get("project_title", "proposal"))[:30]
        pptx_name = f"{title_safe}_초안.pptx"
        pptx_path = DOWNLOAD_DIR / pptx_name

        rc, _ = await run_proc(tid, [
            "node", RENDER_DECK_JS, str(deck_plan), "-o", str(pptx_path),
        ])
        if rc != 0:
            _task_error(tid, "render_deck.js 실패 — node/pptxgenjs 설치를 확인하세요")
            return

        _log(tid, f"🎉 완료!  {pptx_name}")
        _task_done(tid, {"filename": pptx_name, "title": rfp_meta.get("project_title", "")})

    except Exception as e:
        _task_error(tid, str(e))
    finally:
        for f in tmp_files:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass


# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(title="OOTB Proposal UI", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((HERE / "static" / "index.html").read_text(encoding="utf-8"))


@app.get("/api/status")
async def api_status() -> dict:
    env_ok = bool(SB_URL and SB_KEY and GM_KEY)
    doc_count = 0
    if env_ok:
        try:
            rows = await sb_get("proposals", {"select": "id", "limit": "9999"})
            doc_count = len(rows)
        except Exception:
            env_ok = False
    return {"env_ok": env_ok, "doc_count": doc_count}


@app.get("/api/documents")
async def api_list_documents() -> list:
    return await sb_get("proposals", {
        "select": "id,title,client_name,project_year,tags,abstract,created_at",
        "order":  "created_at.desc",
        "limit":  "500",
    })


@app.post("/api/documents/upload")
async def api_upload_document(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드 가능합니다")

    tid = uuid.uuid4().hex[:8]
    _task_start(tid)

    tmp = DOWNLOAD_DIR / f"{tid}_{file.filename}"
    tmp.write_bytes(await file.read())
    background_tasks.add_task(_ingest_task, tid, tmp)
    return {"task_id": tid}


@app.delete("/api/documents/{doc_id}")
async def api_delete_document(doc_id: int) -> dict:
    await sb_delete("proposals", doc_id)
    return {"deleted": doc_id}


@app.post("/api/proposals/generate")
async def api_generate_proposal(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 지원됩니다")

    tid = uuid.uuid4().hex[:8]
    _task_start(tid)

    tmp = DOWNLOAD_DIR / f"{tid}_rfp_{file.filename}"
    tmp.write_bytes(await file.read())
    background_tasks.add_task(_proposal_task, tid, tmp)
    return {"task_id": tid}


@app.get("/api/tasks/{task_id}/stream")
async def api_task_stream(task_id: str) -> StreamingResponse:
    async def gen() -> AsyncGenerator[str, None]:
        sent = 0
        while True:
            logs = _logs.get(task_id, [])
            while sent < len(logs):
                yield f"data: {json.dumps({'log': logs[sent]})}\n\n"
                sent += 1
            st = _status.get(task_id, "running")
            if st != "running":
                yield f"data: {json.dumps({'status': st, 'result': _result.get(task_id, {})})}\n\n"
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/download/{filename}")
async def api_download(filename: str) -> FileResponse:
    safe = Path(filename).name
    path = DOWNLOAD_DIR / safe
    if not path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    return FileResponse(
        path, filename=safe,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


# ── entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7979)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    print(f"\n  🚀  OOTB Web UI  →  http://{args.host}:{args.port}\n")
    if not SB_URL:
        print("  ⚠  SUPABASE_URL 미설정 — python configure_env.py 로 먼저 설정하세요\n")
    if not GM_KEY:
        print("  ⚠  GEMINI_API_KEY 미설정\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
