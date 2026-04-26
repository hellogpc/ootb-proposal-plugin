# 오오티비랩 제안서 자동화 플러그인

Claude Cowork 에 설치해 과거 제안서를 DB 에 쌓고, 새 RFP/과업지시서/공고가 오면 유사 사례를 찾아 **오오티비랩(OOTB Lab) 브랜드 포맷의 제안서 초안 PPT** 를 자동으로 만들어 주는 플러그인.

## 포함된 스킬

| 스킬 | 역할 |
|---|---|
| **`dashboard`** | ⭐ **메인 진입점**. 채팅 안에서 마크다운 카드 + AskUserQuestion으로 대화형 메뉴 제공 |
| `proposal-supabase-sync` | 과거 제안서 PDF 를 Supabase DB + Storage 에 수집하고, 벡터·키워드·메타 하이브리드 검색 제공 |
| `rfp-to-proposal-pipeline` | **오케스트레이터**. 새 RFP → 유사 사례 top-3 검색 → outline.yaml 합성 |
| `ootb-proposal-pptx` | outline.yaml 을 OOTB 브랜드 포맷의 `.pptx` 로 렌더 (pptxgenjs) |

## 2분 시작법

**Claude 채팅창에서:**
```
"대시보드 보여줘"   또는   "메뉴 열어줘"
```
→ 채팅 안에서 상태 카드 + 메뉴가 표시되고, 선택지를 클릭해 모든 기능 사용 가능.

## 초기 설정 (1회)

1. **Supabase MCP 커넥터 연결** — Claude Cowork 설정 → Connectors → Supabase
2. **DB 스키마 적용** — 채팅에서 "DB 처음 셋업해줘"
3. **Vault 시크릿 등록** — Supabase SQL 에디터 또는 MCP `execute_sql`:
   ```sql
   select vault.create_secret('<GEMINI_API_KEY>', 'gemini_api_key', 'Gemini embed');
   select vault.create_secret('<SERVICE_ROLE_KEY>', 'supabase_service_role_key', 'Storage upload');
   ```
4. **Edge Function 배포** — `skills/proposal-supabase-sync/edge-functions/upload-b64/`
5. **SQL 함수 적용** — `sql/002_embed_in_db.sql` → `003_vault_helpers.sql` → `004_upload_via_vault.sql`

이후 모든 작업은 대시보드에서 진행.

## 의존성 (최초 1회)

```bash
pip install -r skills/proposal-supabase-sync/scripts/requirements.txt
pip install -r skills/rfp-to-proposal-pipeline/scripts/requirements.txt
pip install -r skills/ootb-proposal-pptx/scripts/requirements.txt
cd skills/ootb-proposal-pptx/scripts && npm install
```

> **로컬 `.env` 불필요** — 모든 인증(Gemini, Supabase service role)은 Supabase Vault에서 처리됩니다.

## 외부 의존성

- **Supabase** — Postgres + pgvector + Storage + Vault + Edge Functions (MCP)
- **Google Gemini** — Embedding (1536-d). API 키는 Supabase Vault에 보관
- **pptxgenjs** — 플러그인 내 `npm install`
- **LibreOffice + poppler** (선택) — QA 용

## 버전 이력

- **0.5.3** — Storage 업로드를 Edge Function `upload-binary` 직접 HTTP 방식으로 전환 (~50 MB 지원). MCP `execute_sql`의 ~3.4 MB payload 한계 우회.
- 0.5.2 — `configure-env`/`web-ui` 스킬 제거, deprecated 스크립트 정리, 중복 `mcp_playbook.md` 통합. 로컬 `.env` 완전 불필요 (Vault 시크릿만).
- 0.5.1 — `.plugin` 번들·GitHub Action 제거 (마켓플레이스 설치는 repo 직접 참조). 수동 설치는 GitHub Releases 사용.
- 0.5.0 — Env-free 운영 전환. Vault + Edge Function `upload-b64` + `gemini_embed_vault()` + `upload_pdf_via_vault()`로 모든 인증을 DB에서 처리.
- 0.4.0 — `web-ui` 스킬 추가 (이후 0.5.2에서 제거).
- 0.3.1 — `configure-env` TUI 마법사 추가 (이후 0.5.2에서 제거).
- 0.3.0 — `.env`를 사용자 config 위치로 이전.
- 0.2.0 — `configure-env` 스킬 추가 (이후 0.5.2에서 제거).
- 0.1.0 — 초기 릴리스

## 라이선스

내부 자산 (Proprietary).
