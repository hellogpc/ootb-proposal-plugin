---
name: dashboard
description: "MUST USE as the main entry point for OOTB proposal automation. Shows a visual markdown dashboard in the chat with status cards and a menu. Use AskUserQuestion to let users pick actions. Triggers: '대시보드', '메뉴 보여줘', '뭐할 수 있어', 'OOTB 시작', '제안서 자동화 시작', '/dashboard', '어떻게 쓰는거야', '기능 보여줘', '/menu'. After each action completes, offer to return to dashboard."
---

# OOTB Dashboard — 채팅 내 시각 UI

이 스킬은 Claude 채팅 인터페이스 자체를 UI로 사용합니다.  
웹 서버 없이 **마크다운 카드 + AskUserQuestion** 조합으로 대화형 메뉴를 구성합니다.

---

## Claude가 따라야 할 흐름

### Step 1 — 상태 수집

실행 전 두 가지를 조용히 확인 (Supabase MCP 사용):

1. **Vault 시크릿**:  
   `select name from vault.decrypted_secrets where name in ('gemini_api_key','supabase_service_role_key');`  
   → 두 시크릿 존재 여부 확인. MCP 미연결이면 "➖ MCP 미연결".

2. **DB 문서 수**:  
   `select count(*) from proposals;`  
   MCP 연결 안 됐으면 "—" 표시.

### Step 2 — 대시보드 렌더링

아래 형식을 그대로 출력한다 (상태값만 채워서):

```
---
## 🔷 OOTB 제안서 자동화

| | 항목 | 상태 |
|:---:|---|---|
| 🔐 | Vault 시크릿 | ✅ 등록됨 / ❌ 미등록 / ➖ MCP 미연결 |
| 🗄️ | DB 연결 | ✅ 연결됨 / ❌ 미연결 / ➖ MCP 미연결 |
| 📁 | 등록 제안서 | **N건** / — |

---

### 무엇을 할까요?

| | 메뉴 | 설명 |
|:---:|---|---|
| 📂 | **문서 등록** | 과거 제안서 PDF를 DB에 수집 |
| 📋 | **문서 목록** | 등록된 제안서 조회 및 삭제 |
| ✨ | **제안서 작성** | RFP → 유사 사례 검색 → PPT 초안 생성 |

---
```

> Vault 시크릿이 미등록이면 메뉴 아래에 안내 추가:
> ```sql
> select vault.create_secret('<GEMINI_API_KEY>', 'gemini_api_key', 'Gemini embed');
> select vault.create_secret('<SERVICE_ROLE_KEY>', 'supabase_service_role_key', 'Storage');
> ```

### Step 3 — AskUserQuestion으로 메뉴 선택

```
AskUserQuestion(
  question: "원하는 기능을 선택하세요",
  options: ["📂 문서 등록", "📋 문서 목록", "✨ 제안서 작성"]
)
```

---

## 각 메뉴 처리

### 📂 문서 등록

```
AskUserQuestion(
  question: "등록할 제안서 PDF 경로를 입력하세요\n(여러 파일은 쉼표로 구분)",
  type: text
)
```

경로 받은 후:
1. 파일별로 `proposal-supabase-sync` Path B 실행
2. 진행 결과를 아래 형식으로 출력:

```
---
### 📂 문서 등록 결과

| 파일 | 제목 | 연도 | ID | 결과 |
|---|---|---|---|---|
| 복지로_2025.pdf | 복지로 SNS 전략 제안 | 2025 | 23 | ✅ 등록 |
| 수산물.pdf | 수산물이력제 홍보 | 2024 | 24 | ✅ 등록 |

총 **2건** 등록 완료.

---
```

완료 후 → "다른 작업을 할까요?" + AskUserQuestion(["🏠 메뉴로 돌아가기", "📂 추가 등록", "✨ 제안서 바로 작성"])

---

### 📋 문서 목록

Supabase MCP로 조회:
```sql
select id, title, client_name, project_year, tags, abstract
from proposals
order by created_at desc
limit 20;
```

결과를 아래 형식으로 출력:

```
---
### 📋 등록된 제안서 (총 N건, 최신 20건 표시)

| ID | 제목 | 발주처 | 연도 | 태그 |
|---|---|---|---|---|
| 23 | 복지로 SNS 전략 제안 | 복지부 | 2025 | `복지` `SNS` `숏폼` |
| 22 | 수산물이력제 홍보사업 | 해수부 | 2025 | `수산` `이력제` |
| … | … | … | … | … |

---
```

이후 AskUserQuestion(["🗑️ 특정 문서 삭제", "🏠 메뉴로 돌아가기"])

삭제 선택 시:
```
AskUserQuestion(
  question: "삭제할 제안서 ID를 입력하세요",
  type: text
)
```
→ `delete from proposals where id = N;` 실행 → "✅ id=N 삭제 완료" 출력

---

### ✨ 제안서 작성

```
---
### ✨ 제안서 작성

**진행 순서**
1. RFP/과업지시서 PDF 경로 입력
2. 유사 사례 top-3 검색
3. Gemini가 outline.yaml 합성
4. pptxgenjs로 PPT 렌더링

---
```

```
AskUserQuestion(
  question: "RFP / 과업지시서 PDF 경로를 입력하세요",
  type: text
)
```

경로 받은 후 `rfp-to-proposal-pipeline` 전체 워크플로우 실행.

각 단계마다 진행 상황을 인라인으로 출력:

```
⏳ **[1/6] RFP 분석 중...** `prep_rfp.py` 실행
✅ **[1/6] 완료** — 사업명: 2026년 수산물이력제 홍보사업

⏳ **[2/6] 유사 사례 검색 중...**
✅ **[2/6] 완료** — 3건 발견

| # | 제목 | 연도 | 유사도 |
|---|---|---|---|
| 1 | 복지로 SNS 전략 | 2025 | 0.87 |
| 2 | 해양수산부 이력제 | 2024 | 0.81 |
| 3 | 환경부 캠페인 | 2024 | 0.73 |

⏳ **[3/6] outline.yaml 합성 중 (Gemini)...**
✅ **[3/6] 완료** — 슬라이드 14장 구성

⏳ **[4/6] 구조 검증 중...**
✅ **[4/6] 통과**

⏳ **[5/6] deck_plan.json 빌드 중...**
✅ **[5/6] 완료**

⏳ **[6/6] PPT 렌더링 중 (pptxgenjs)...**
✅ **[6/6] 완료**
```

완료 후 출력:

```
---
### 🎉 제안서 초안 완성!

| 항목 | 내용 |
|---|---|
| 사업명 | 2026년 수산물이력제 홍보사업 |
| 슬라이드 수 | 14장 |
| 참고 사례 | 3건 |
| 저장 경로 | `/tmp/수산물이력제_초안.pptx` |

> ⚠️ 초안입니다. 예산·날짜·인명은 반드시 검토 후 수정하세요.

---
```

완료 후 → AskUserQuestion(["🏠 메뉴로 돌아가기", "📂 다른 RFP로 작성", "📋 문서 목록 보기"])

---

## 안티패턴

- ❌ 상태 확인 없이 바로 메뉴 출력
- ❌ 선택지 없이 텍스트로만 안내
- ❌ 각 단계 완료 후 메뉴로 돌아갈 기회 미제공
- ❌ 진행 단계를 건너뛰어 요약만 출력
