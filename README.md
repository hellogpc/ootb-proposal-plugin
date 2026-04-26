# 오오티비랩 제안서 자동화 플러그인

Claude Cowork 에 설치해 과거 제안서를 DB 에 쌓고, 새 RFP/과업지시서/공고가 오면 유사 사례를 찾아 **오오티비랩(OOTB Lab) 브랜드 포맷의 제안서 초안 PPT** 를 자동으로 만들어 주는 플러그인.

## 포함된 스킬

| 스킬 | 역할 |
|---|---|
| **`configure-env`** | 터미널 TUI 마법사로 Gemini/Supabase 키를 대화식 입력 · 검증 · 저장 |
| `proposal-supabase-sync` | 과거 제안서 PDF 를 Supabase DB + Storage 에 수집하고, 벡터·키워드·메타 하이브리드 검색 제공 |
| `rfp-to-proposal-pipeline` | **오케스트레이터**. 새 RFP → 유사 사례 top-3 검색 → outline.yaml 합성 |
| `ootb-proposal-pptx` | outline.yaml 을 OOTB 브랜드 포맷의 `.pptx` 로 렌더 (pptxgenjs) |
| **`web-ui`** | 로컬 웹 UI (FastAPI + 브라우저). 문서 업로드 · 목록 · 삭제 / RFP → PPT 초안 생성 · 다운로드 |

## 2분 시작법

**Claude 채팅창에서 (MCP 경로):**
```
1. "Supabase MCP 커넥터 설정 도와줘"           # Claude Settings → Connectors → Supabase
2. "환경변수 설정해줘"                           # TUI 마법사로 Gemini/Supabase 키 입력
3. "DB 처음 셋업해줘"                            # 스키마 자동 적용
4. "이 PDF 등록해줘: <경로>"                     # 과거 제안서 수집
5. "이 RFP 로 제안서 초안 짜줘: <경로>"          # ⭐ 핵심 기능
```

**브라우저 UI로 사용하기 (web-ui):**
```bash
pip install -r skills/web-ui/scripts/requirements.txt
python skills/web-ui/scripts/server.py
# → http://localhost:7979 접속
```

## `.env` 저장 위치 (v0.3.0 부터)

플러그인 디렉터리는 read-only 이므로 설정은 **사용자가 쓸 수 있는 OS별 표준 위치**에 저장됩니다:

| OS | 경로 |
|---|---|
| macOS | `~/Library/Application Support/ootb-proposal-automation/.env` |
| Linux | `~/.config/ootb-proposal-automation/.env` |
| Windows | `%APPDATA%\ootb-proposal-automation\.env` |

`configure-env` 스킬이 자동으로 위 경로에 쓰고, 모든 consumer 스크립트가 같은 위치를 찾습니다.

### override 가능
- `$OOTB_ENV_FILE` 환경변수로 특정 파일 경로 override
- `configure_env.py --target /custom/path/.env` 로 커스텀 위치 지정

## 의존성 (최초 1회)

```bash
pip install -r skills/configure-env/scripts/requirements.txt          # TUI 마법사 (rich, questionary)
pip install -r skills/proposal-supabase-sync/scripts/requirements.txt
pip install -r skills/rfp-to-proposal-pipeline/scripts/requirements.txt
pip install -r skills/ootb-proposal-pptx/scripts/requirements.txt
pip install -r skills/web-ui/scripts/requirements.txt                 # 웹 UI (fastapi, uvicorn, httpx)
cd skills/ootb-proposal-pptx/scripts && npm install
```

## 외부 의존성

- **Supabase** — Postgres + pgvector + Storage (MCP + HTTP)
- **Google Gemini** — Chat + Embedding (1536-d)
- **pptxgenjs** — 플러그인 내 `npm install`
- **LibreOffice + poppler** (선택) — QA 용

## 버전 이력

- **0.4.0** — `web-ui` 스킬 추가. 브라우저로 문서 업로드·목록·삭제·제안서 생성 가능.
- 0.3.1 — `configure-env` TUI 마법사 추가 (rich + questionary). `prep.py` `--full-json` 플래그 추가.
- 0.3.0 — `.env`를 사용자 config 위치로 이전. 공통 `_env.py` 리졸버 도입.
- 0.2.0 — `configure-env` 스킬 추가
- 0.1.0 — 초기 릴리스

## 라이선스

내부 자산 (Proprietary).
