---
name: configure-env
description: "Set or update plugin env vars (Gemini, Supabase) without manually editing .env. Triggers: '환경변수 설정', '키 세팅', '.env 만들어줘', 'Gemini 키 넣어줘', 'Supabase 키 바꿔줘', '키 로테이션', '/setup-env', 'configure env'. Also auto-runs at first DB request if .env is missing. Collects keys via AskUserQuestion, writes to a user-writable location (~/Library/Application Support/ootb-proposal-automation/.env on macOS) with atomic write + backup + mode 600, optionally validates with live HTTP checks. Do NOT use for MCP connector setup (that's in Claude UI)."
---

# configure-env — 플러그인 환경변수 설정

이 스킬은 플러그인의 `.env`를 **사용자가 손으로 편집하지 않고** 대화식으로 생성/갱신합니다.

## 중요 — 설치 디렉터리는 read-only

플러그인 파일 자체는 `${CLAUDE_PLUGIN_ROOT}` 아래에 read-only 로 설치됩니다. 그 안에 `.env`를 쓰려 하면 **Permission denied**. 이 스킬은 사용자가 쓸 수 있는 OS별 표준 위치에 `.env`를 만듭니다:

| OS | 기본 위치 |
|---|---|
| macOS | `~/Library/Application Support/ootb-proposal-automation/.env` |
| Linux | `$XDG_CONFIG_HOME/ootb-proposal-automation/.env` (기본 `~/.config/...`) |
| Windows | `%APPDATA%\ootb-proposal-automation\.env` |

모든 consumer 스크립트(`prep.py`, `prep_rfp.py`, `embed_query.py`, `upload_storage.py`)는 번들된 `_env.py` 리졸버를 통해 위 위치를 최우선으로 찾습니다.

### 찾는 순서
1. `$OOTB_ENV_FILE` 환경변수 override
2. OS별 user config 위치 (위 표)
3. `$CLAUDE_PLUGIN_ROOT/skills/proposal-supabase-sync/scripts/.env` (레거시)
4. 스크립트와 같은 디렉터리의 `.env` (개발 모드)

## 트리거 예시

- "환경변수 설정해줘", "키 세팅 해줘"
- "Gemini 키 넣어줘", "Supabase 키 바꿔줘"
- ".env 만들어줘", ".env 채워줘"
- "키 로테이션"
- `/setup-env`, `/configure-env`, `configure env`

**first-run 감지**: 사용자가 DB 작업(등록/검색/셋업)을 요청했는데 위 검색 순서로도 `.env`를 못 찾으면 이 스킬을 먼저 실행해 키를 받고 이후 원래 요청을 이어서 수행할 것.

## Claude 가 따라야 할 순서

1. **현재 상태 확인** (플러그인 root 에서 _env 리졸버 실행)
   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/skills/configure-env/scripts/_env.py"
   ```
   이미 어딘가에 `.env` 가 있으면 "교체할까요, 누락된 키만 채울까요?" 로 확인.

2. **AskUserQuestion 으로 값 받기** — 민감값은 반드시 이 도구 경유:

   | key | 질문 | 필수 | 기본값 |
   |-----|------|------|--------|
   | `GEMINI_API_KEY` | "Google AI Studio 의 Gemini API 키(`AIza...`)" | ✅ | — |
   | `SUPABASE_URL`   | "Supabase 프로젝트 URL (`https://<ref>.supabase.co`)" | ✅ | — |
   | `SUPABASE_SERVICE_ROLE_KEY` | "Service Role Key (`eyJ...` JWT)" | ✅ | — |
   | `SUPABASE_BUCKET` | "Storage 버킷 이름" | ⬜ | `proposals` |
   | `GEMINI_CHAT_MODEL` | "Gemini Chat 모델" | ⬜ | `gemini-2.5-flash` |
   | `GEMINI_EMBED_MODEL` | "Gemini Embedding 모델" | ⬜ | `gemini-embedding-001` |
   | `EMBED_DIM` | "임베딩 차원 (DB column 과 일치)" | ⬜ | `1536` |

3. **`.env` 쓰기** — 번들된 헬퍼 스크립트 사용:
   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/skills/configure-env/scripts/configure_env.py" \
     --gemini-key     "$GEMINI_API_KEY" \
     --supabase-url   "$SUPABASE_URL" \
     --supabase-key   "$SUPABASE_SERVICE_ROLE_KEY" \
     --bucket         "${SUPABASE_BUCKET:-proposals}" \
     --gemini-chat-model  "${GEMINI_CHAT_MODEL:-gemini-2.5-flash}" \
     --gemini-embed-model "${GEMINI_EMBED_MODEL:-gemini-embedding-001}" \
     --embed-dim      "${EMBED_DIM:-1536}" \
     --validate
   ```

   헬퍼 동작:
   - 기본 target: OS별 user config 위치 (위 표)
   - `--target /path` 로 override 가능
   - 기존 파일 있으면 `.env.bak.<timestamp>` 로 자동 백업
   - 원자적 쓰기 (`.env.new` → `os.replace`)
   - mode 600 설정
   - `--validate` 로 Supabase REST + Gemini Embedding 엔드포인트 라이브 확인

4. **성공 보고**:
   > ✅ 환경변수 설정 완료 (`<경로>`). 이제 `proposal-supabase-sync` 스킬이 바로 동작합니다.
   > 다음 단계: *"DB 처음 셋업해줘"* 또는 *"이 PDF 등록해줘"*

## Vault 로테이션 플로우

사용자가 "Gemini 키 로테이션", "Supabase 키 바꿔줘" 라고 하면:
1. 위 단계 그대로 (새 키로 `.env` 덮어씀 — 이전 값은 `.env.bak` 로 백업됨)
2. Supabase MCP `execute_sql` 로 Vault 시크릿 갱신:
   ```sql
   update vault.secrets set secret = '<new_gemini>'       where name = 'gemini_api_key';
   update vault.secrets set secret = '<new_service_role>' where name = 'supabase_service_role_key';
   ```
3. 구키를 Google AI Studio / Supabase Dashboard 에서 revoke 하라고 안내

## 마이그레이션 — 기존 사용자

플러그인 이전 버전(v0.2.x)을 쓰고 있었다면 `.env`가 스킬 디렉터리 안에 있었을 수 있음. 이 경우:
1. 플러그인 재설치 시 기존 `.env`가 사라질 수 있음 (read-only 디렉터리 교체됨)
2. 이 스킬을 한 번 다시 실행하면 됨 — 같은 키로 user config 위치에 재생성
3. `_env.py` 리졸버는 레거시 위치도 여전히 찾아보므로 재설정 전에도 동작은 함

## 안티패턴

- ❌ 플러그인 디렉터리 내부에 `.env` 를 쓰려는 시도 (permission denied)
- ❌ AskUserQuestion 없이 채팅창에 평문 키 붙여넣게 함 (보안)
- ❌ 기존 `.env` 덮어쓸 때 백업 안 만들기
- ❌ 검증 없이 "완료" 보고
