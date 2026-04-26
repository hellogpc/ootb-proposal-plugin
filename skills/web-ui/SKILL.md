---
name: web-ui
description: "Launch a local web UI for OOTB proposal automation — document upload and proposal generation via browser. Triggers: 'UI 실행', '웹으로 쓰고 싶어', '브라우저 UI', 'web UI 켜줘', '인터페이스 실행', '웹 인터페이스'. Requires configure-env + Supabase DB setup to be done first."
---

# OOTB Web UI

브라우저 기반 로컬 웹 UI로 제안서 문서를 관리하고 RFP로부터 PPT 초안을 생성합니다.

## 실행

```bash
# 1. 의존성 설치 (최초 1회)
pip install -r "$CLAUDE_PLUGIN_ROOT/skills/web-ui/scripts/requirements.txt"

# 2. 서버 시작
python "$CLAUDE_PLUGIN_ROOT/skills/web-ui/scripts/server.py"
# → http://localhost:7979 에서 접속
```

포트 변경: `--port 8080`

## 기능

| 탭 | 기능 |
|---|---|
| **문서 관리** | PDF 드래그&드롭 업로드 → Gemini 분석 → Supabase 저장 / 목록 조회 / 삭제 |
| **제안서 작성** | RFP PDF 업로드 → 유사 사례 검색 → Gemini outline 합성 → PPT 렌더링 → 다운로드 |

## 사전 조건

1. `configure-env` 스킬로 `.env` 설정 완료
2. `proposal-supabase-sync` Path A (DB 스키마 적용) 완료
3. `ootb-proposal-pptx` npm install 완료 (`node render_deck.js` 실행 가능 상태)

## 안티패턴

- `CLAUDE_PLUGIN_ROOT`가 설정되지 않은 경우 스크립트 경로 자동 추론 (스킬 디렉터리 기준 `../../..`)
- 서버는 127.0.0.1에만 바인딩 — 외부 노출 금지
