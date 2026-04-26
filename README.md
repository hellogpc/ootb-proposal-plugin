# 오오티비랩 제안서 자동화 플러그인

Claude Cowork 에 설치해 과거 제안서를 DB 에 쌓고, 새 RFP/과업지시서/공고가 오면 유사 사례를 찾아 **오오티비랩(OOTB Lab) 브랜드 포맷의 제안서 초안 PPT** 를 자동으로 만들어 주는 플러그인.

## 시스템 구조

```
┌──────────────────────────────────────────────────────────────────┐
│                        Claude Cowork (Mac)                        │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Plugin: ootb-proposal-automation (GitHub 마켓플레이스)    │    │
│  │  ├─ dashboard              ⭐ 메인 진입점                    │    │
│  │  ├─ proposal-supabase-sync   PDF 등록·검색                 │    │
│  │  ├─ rfp-to-proposal-pipeline RFP → outline.yaml          │    │
│  │  └─ ootb-proposal-pptx       outline → .pptx              │    │
│  └─────────────┬──────────────────────────┬─────────────────┘    │
│                │                           │                       │
│        Supabase MCP                  로컬 Python                  │
│       (SQL 실행, 메타데이터)          (PDF 텍스트 추출)              │
└────────────────┼───────────────────────────┼──────────────────────┘
                 │                           │
                 │                           │ HTTP POST (PDF 바이너리)
                 ▼                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                          Supabase                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐     │
│  │  Postgres    │  │ Edge Function│  │      Vault          │     │
│  │  proposals   │  │ upload-binary│  │ • gemini_api_key    │     │
│  │  (pgvector)  │  │   (~50MB)    │  │ • service_role_key  │     │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘     │
│         │                  │                    │                │
│         │   ┌──────────────┴────────────────────┘                │
│         ▼   ▼                                                    │
│  ┌──────────────┐                                                │
│  │   Storage    │  ← Edge Function이 Vault 키로 직접 PUT          │
│  │   proposals/ │                                                │
│  └──────────────┘                                                │
│                                                                  │
│  Gemini API ◀── gemini_embed_vault(text) — DB가 Vault 키로 호출    │
└──────────────────────────────────────────────────────────────────┘
```

## 데이터 흐름

### 📂 PDF 등록
```
PDF 파일
  → prep.py (텍스트 추출)
  → Edge Function upload-binary (HTTP POST 바이너리)  → Storage
  → Claude (구조화 추출: 제목·태그·요약)
  → MCP execute_sql + gemini_embed_vault()  → Postgres (메타+벡터)
```

### 🔍 검색
```
질의문 → MCP execute_sql:
  match_proposals(query_text, gemini_embed_vault(query_text))
  → top-N 유사 제안서
```

### ✨ 제안서 작성 (RFP → PPT)
```
RFP PDF
  → prep_rfp.py (텍스트만)
  → Claude (RFP 구조화)
  → match_proposals_with_url() (유사 사례 top-3 + signed URL)
  → Claude (outline.yaml 합성)
  → render_deck.js (pptxgenjs) → .pptx
```

## 포함된 스킬

| 스킬 | 역할 |
|---|---|
| **`dashboard`** | ⭐ 메인 진입점. 채팅 안 마크다운 카드 + AskUserQuestion 으로 대화형 메뉴 |
| `proposal-supabase-sync` | 과거 제안서 PDF 를 Supabase DB + Storage 에 수집, 하이브리드 검색 |
| `rfp-to-proposal-pipeline` | RFP → 유사 사례 top-3 검색 → outline.yaml 합성 |
| `ootb-proposal-pptx` | outline.yaml 을 OOTB 브랜드 포맷의 `.pptx` 로 렌더 |

## 설치

### 1단계 — Supabase 준비 (관리자가 1회)

**Vault 시크릿 등록** (Supabase SQL 에디터 또는 MCP `execute_sql`):
```sql
select vault.create_secret('<GEMINI_API_KEY>',  'gemini_api_key',         'Gemini embed');
select vault.create_secret('<SERVICE_ROLE_KEY>','supabase_service_role_key','Storage upload');
```

**스키마 + 함수 적용** (`apply_migration` 으로 순서대로):
- `sql/001_init.sql` — `proposals` 테이블 + `match_proposals` RPC
- `sql/002_embed_in_db.sql` — `http` 확장 + `gemini_embed(text, key)`
- `sql/003_vault_helpers.sql` — `gemini_embed_vault`, `sign_storage_url`, `match_proposals_with_url`
- `sql/004_upload_via_vault.sql` — (legacy 보조)

**Edge Functions 배포**:
- `edge-functions/upload-binary/` ← 메인 (HTTP 바이너리, ~50MB)
- `edge-functions/upload-b64/`    ← 보조 (base64, ~10MB)

### 2단계 — 팀원 PC (각자 1회)

1. **Cowork** → 설정 → Connectors → **Supabase MCP** 연결
2. **마켓플레이스 추가**: `https://github.com/hellogpc/ootb-proposal-plugin`
3. **플러그인 설치**: `ootb-proposal-automation`
4. **Python 의존성**:
   ```bash
   pip install -r skills/proposal-supabase-sync/scripts/requirements.txt
   pip install -r skills/rfp-to-proposal-pipeline/scripts/requirements.txt
   pip install -r skills/ootb-proposal-pptx/scripts/requirements.txt
   cd skills/ootb-proposal-pptx/scripts && npm install
   ```

> ✅ **로컬 `.env` 불필요** — 모든 인증은 Supabase Vault에 보관됨

## 일상 사용

Cowork 채팅창에서 한 마디:

| 상황 | 명령 |
|---|---|
| 메뉴 열기 | `"대시보드 보여줘"` |
| 새 PDF 등록 | `"이 PDF 등록해줘"` + 파일 첨부 |
| 과거 사례 검색 | `"복지 관련 제안서 찾아줘"` |
| 제안서 초안 생성 | `"이 RFP로 제안서 만들어줘"` + 파일 첨부 |
| 등록 현황 | `"DB에 몇 건 있지?"` |

대시보드가 상태 카드(Vault 시크릿 / DB 연결 / 등록 건수)를 표시한 후, 메뉴 선택으로 진행합니다.

## 디렉터리

```
ootb-proposal-plugin/
├── .claude-plugin/
│   ├── plugin.json          # 플러그인 매니페스트
│   └── marketplace.json     # 마켓플레이스 항목
└── skills/
    ├── dashboard/                 ⭐ 메인 진입점 (대화형 메뉴)
    ├── proposal-supabase-sync/    PDF 등록·검색
    │   ├── scripts/prep.py        텍스트 추출 + HTTP 업로드
    │   ├── sql/                   001~004 마이그레이션
    │   └── edge-functions/        upload-binary, upload-b64
    ├── rfp-to-proposal-pipeline/  RFP → outline 합성
    └── ootb-proposal-pptx/        outline → .pptx (pptxgenjs)
```

## 핵심 설계 원칙

| 원칙 | 구현 |
|---|---|
| **시크릿은 DB에만** | Gemini·service role 키 모두 Supabase Vault. 로컬·git에 평문 키 없음 |
| **MCP가 메인 채널** | Claude ↔ DB 통신은 모두 `execute_sql` |
| **바이너리는 HTTP로** | PDF는 Edge Function 직접 POST (~50MB). MCP의 3.4MB 한계 우회 |
| **임베딩은 DB-side** | `gemini_embed_vault(text)` 한 줄. 로컬 Gemini 호출 없음 |
| **Plugin은 read-only** | git 마켓플레이스 → Cowork 자동 동기화. GitHub이 진실의 원천 |

## 외부 의존성

- **Supabase** — Postgres + pgvector + Storage + Vault + Edge Functions (MCP)
- **Google Gemini** — Embedding (1536-d). API 키는 Vault
- **pptxgenjs** — 플러그인 내 `npm install`
- **LibreOffice + poppler** (선택) — QA 용

## 버전 이력

- **0.5.3** — Storage 업로드를 Edge Function `upload-binary` 직접 HTTP 방식으로 전환 (~50 MB 지원). MCP `execute_sql`의 ~3.4 MB payload 한계 우회.
- 0.5.2 — `configure-env`/`web-ui` 스킬 제거, deprecated 스크립트 정리. 로컬 `.env` 완전 불필요.
- 0.5.1 — `.plugin` 번들·GitHub Action 제거 (마켓플레이스 설치는 repo 직접 참조).
- 0.5.0 — Env-free 운영 전환. Vault + Edge Function `upload-b64` + `gemini_embed_vault()`.
- 0.4.0 — `web-ui` 스킬 추가 (이후 0.5.2에서 제거).
- 0.3.x — `configure-env` TUI / 사용자 config 위치 (이후 0.5.2에서 제거).
- 0.2.0 — `configure-env` 스킬 추가 (이후 0.5.2에서 제거).
- 0.1.0 — 초기 릴리스

## 라이선스

내부 자산 (Proprietary).
