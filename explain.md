# HY-Plan 시스템 동작 구조 설명

## 전체 아키텍처 개요

이 프로젝트는 프론트엔드(React)와 백엔드(Python)가 분리된 웹 애플리케이션이다.

```
┌─────────────────────────────────────────────────────────────────┐
│  프론트엔드 (React + TypeScript + Vite)                          │
│  front/2026_MAR_HACKERTHON/                                     │
│                                                                 │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 로그인/   │  │ Dashboard    │  │ 졸업사정     │              │
│  │ 회원가입  │  │ (ChatInterface│  │ (GraduationAudit)│          │
│  │ Modal    │  │  + Sidebar)  │  │              │              │
│  └──────────┘  └──────┬───────┘  └──────────────┘              │
│                       │                                         │
│              llmService.ts                                      │
│              fetch('/api/chat')                                  │
│                       │                                         │
│              Vite Dev Proxy                                      │
│              /api → localhost:8000                               │
└───────────────────────┼─────────────────────────────────────────┘
                        │ HTTP (JSON)
┌───────────────────────┼─────────────────────────────────────────┐
│  백엔드 (Python FastAPI)  localhost:8000                         │
│  src/                                                           │
│                                                                 │
│  POST /api/chat  { message: "..." }                             │
│       │                                                         │
│       ↓                                                         │
│  ChatBot.handle_input()                                         │
│       │                                                         │
│       ↓                                                         │
│  IntentRouter → 의도 분류 (키워드 매칭)                           │
│       │                                                         │
│  ┌────┴────┬────────┬────────┬────────┬────────┐               │
│  ↓         ↓        ↓        ↓        ↓        ↓               │
│ RAG Q&A  시간표   일정조회  학점확인  수강포기  재수강            │
│          추천                                                   │
│                                                                 │
│  규칙 엔진: CreditValidator, ConflictChecker,                    │
│            PrerequisiteChecker, CancellationChecker,             │
│            EquivalentManager, CurriculumAdvisor                  │
│                                                                 │
│  RAG: Chroma 벡터DB + OpenAI 임베딩 + GPT-4o                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 프론트엔드 상세

### 기술 스택

| 기술 | 용도 |
|------|------|
| React 18 + TypeScript | UI 프레임워크 |
| Vite | 빌드 도구 + 개발 서버 |
| TailwindCSS 4 | 스타일링 |
| Radix UI | 기본 UI 컴포넌트 (Dialog, Tabs 등) |
| MUI | 아이콘, 추가 UI 컴포넌트 |
| Supabase | 인증 (회원가입/로그인/세션관리) |
| Framer Motion | 애니메이션 |
| Recharts | 차트 |

### 화면 구조

```
[비로그인 상태]
┌─────────────────────────────────────────┐
│ Header (홈 / 소개 / 문의)                │
├────────┬────────────────────────────────┤
│ 사이드  │                                │
│ ─ 로고  │     HY-Plan                    │
│ ─ 회원  │     한양대학교 학생들을 위한     │
│   가입  │     스마트한 시간표 및           │
│ ─ 로그  │     일정 관리 플랫폼            │
│   인    │                                │
├────────┴────────────────────────────────┤
│ Footer                                   │
└─────────────────────────────────────────┘

[로그인 후]
┌────────┬────────────────────────────────┐
│Sidebar │  ChatInterface (HY-Planner)    │
│        │  또는                           │
│─HY-    │  GraduationAudit (졸업사정)     │
│ Planner│                                │
│─졸업   │  ┌────────────────────────┐    │
│ 사정   │  │ "OOO님, 안녕하세요"     │    │
│─한양대 │  │ "무엇을 도와드릴까요?"   │    │
│ 홈(외) │  │                        │    │
│─포털   │  │ [수강신청] [학사일정]    │    │
│ (외부) │  │ [시간표]  [학식메뉴]    │    │
│─증명   │  │                        │    │
│ 발급   │  │ ┌──────────────────┐   │    │
│─학식   │  │ │ 입력창            │   │    │
│─학사   │  │ └──────────────────┘   │    │
│ 일정   │  └────────────────────────┘    │
│─시설   │                                │
│ 대관   │                                │
│        │                                │
│[로그   │                                │
│ 아웃]  │                                │
└────────┴────────────────────────────────┘
```

### 주요 컴포넌트

1. `App.tsx` — 루트 컴포넌트. 로그인 상태에 따라 랜딩 페이지 또는 Dashboard를 렌더링
2. `Dashboard.tsx` — 로그인 후 메인 레이아웃. Sidebar + 콘텐츠 영역
3. `Sidebar.tsx` — 좌측 네비게이션. 내부 메뉴(HY-Planner, 졸업사정)와 외부 링크(포털, 학식 등)
4. `ChatInterface.tsx` — 챗봇 UI. 초기 화면(인사말 + 제안 칩) → 대화 모드(메시지 목록)
5. `GraduationAudit.tsx` — 졸업사정 수동 입력/관리 페이지. 전공/교양 학점 현황 테이블
6. `LoginModal.tsx` / `SignUpModal.tsx` — 인증 모달

### 인증 흐름 (Supabase)

```
사용자 → SignUpModal → authService.signUp()
                            │
                            ↓
                      Supabase Auth API
                      (VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY)
                            │
                            ↓
                      이메일 확인 → 로그인 가능
                            │
사용자 → LoginModal → authService.signIn()
                            │
                            ↓
                      세션 생성 → App에서 isLoggedIn=true
                            │
                            ↓
                      Dashboard 렌더링
```

Supabase 환경변수가 없으면 mock 모드로 동작한다 (개발용).

### 프론트엔드 → 백엔드 통신

`llmService.ts`가 유일한 백엔드 통신 레이어다.

```typescript
// llmService.ts
const API_BASE = '/api';

export async function sendMessage(message: string): Promise<string> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  const data = await response.json();
  return data.answer;
}
```

Vite 개발 서버가 `/api` 경로를 `http://localhost:8000`으로 프록시한다:

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
},
```

### 졸업사정 데이터 관리

`GraduationContext.tsx`가 졸업 이수 현황을 전역 상태로 관리한다.

- 데이터 저장: 브라우저 `localStorage` (`hy-plan-graduation` 키)
- 관리 항목: 졸업 전체 학점, 전공(100/200~300/400단위), 교양(핵심교양, 고전읽기, 선택 5영역)
- `remainingSummary` 속성으로 잔여 학점 요약 문자열을 챗봇에 제공 가능

---

## 백엔드 상세

### 기술 스택

| 기술 | 용도 |
|------|------|
| Python | 메인 언어 |
| FastAPI | REST API 서버 (localhost:8000) |
| LangChain | RAG 파이프라인 구성 |
| OpenAI GPT-4o | LLM 답변 생성 |
| OpenAI text-embedding-3-small | 텍스트 임베딩 |
| Chroma | 벡터 DB (로컬 파일) |
| rich | CLI 출력 (독립 실행 시) |

### 시작 시 초기화 과정

```
1. data.md 읽기 (학사안내 원문)
       │
       ↓  PageParser
2. 페이지 분리 (--- 페이지 N --- 구분자)
       │
       ↓  DataParser
3. 6개 영역으로 구조화 (ParsedData)
       ├── schedule          (수강신청/정정/포기 일정)
       ├── credit_rules      (학점 상한/하한 규칙)
       ├── cancel_rules      (폐강 기준)
       ├── prerequisites     (선수-후수 관계)
       ├── equivalent_courses (동일/대치 교과목)
       └── curriculum_rules  (교육과정 적용 규칙)
       │
       ↓
4. 벡터 DB 인덱싱
       페이지 텍스트 → 800자 청크 분할 → OpenAI 임베딩 → Chroma 저장
       │
       ↓
5. 규칙 엔진 초기화
       ├── CreditValidator      (학점 범위 검증)
       ├── ConflictChecker      (시간 충돌 검사)
       ├── PrerequisiteChecker  (선수과목 확인)
       ├── CancellationChecker  (폐강 위험 판정)
       ├── EquivalentManager    (동일/대치 교과목)
       └── CurriculumAdvisor    (교육과정 적용)
              │
              ↓
       ScheduleRecommender (위 검증기 통합)
       │
       ↓
6. ChatBot 인스턴스 생성 → API 서버 시작
```

### 의도 분류 및 처리 흐름

```
프론트엔드 요청: POST /api/chat { message: "3학년 수강신청 일정 알려줘" }
       │
       ↓
ChatBot.handle_input()
       │
       ↓  IntentRouter.classify() — 키워드 매칭
       │
       ├── "수강신청 일정" → SCHEDULE_INFO
       │     → ParsedData에서 해당 학년 일정 조회
       │
       ├── "시간표" → SCHEDULE_RECOMMEND
       │     → 필수 정보 수집 안내 메시지
       │
       ├── "학점" → CREDIT_CHECK
       │     → RAG 파이프라인으로 학점 관련 답변
       │
       ├── "수강포기" → DROP_CHECK
       │     → ParsedData에서 수강포기 일정/조건 조회
       │
       ├── "재수강" → RETAKE_INFO
       │     → 재수강 규칙 안내
       │
       └── 매칭 없음 → REGULATION_QA
             → RAG: 벡터 DB 검색 → LLM 답변 생성
       │
       ↓
응답: { answer: "📅 3학년 수강신청 일정\n• ..." }
```

### RAG Q&A 동작

```
질문: "수강정정 기간이 언제야?"
       │
       ↓  OpenAI 임베딩
질문 벡터
       │
       ↓  Chroma similarity_search (top-5, 유사도 ≥ 0.3)
유사 청크 검색
       │
       ↓  컨텍스트 구성
"[페이지 5] 수강정정 일정은..."
       │
       ↓  ChatOpenAI (gpt-4o, temperature=0)
시스템 프롬프트: "한양대 학사안내 전문 도우미. 참고 자료만 근거로 답변."
       │
       ↓
답변 + 출처 페이지 번호
```

근거가 없으면 "해당 정보를 찾을 수 없습니다" 반환.

---

## 데이터 흐름 요약

```
[사용자]
   │
   ↓ 브라우저
[React 프론트엔드 — Vite dev server :5173]
   │
   ├── 인증 ──→ Supabase Auth (외부 서비스)
   │
   ├── 졸업사정 ──→ localStorage (브라우저 로컬)
   │
   └── 챗봇 질문 ──→ /api/chat (Vite proxy)
                        │
                        ↓
              [Python 백엔드 — FastAPI :8000]
                        │
                        ├── 규칙 기반 응답 (ParsedData 조회)
                        │
                        └── RAG 응답
                              ├── Chroma 벡터 DB (로컬 파일)
                              └── OpenAI API (임베딩 + LLM)
```

---

## 실행 방법

### 백엔드

```bash
# .env 파일에 OPENAI_API_KEY 설정
python -m src.main
# 또는 FastAPI 서버로 실행
# uvicorn src.api:app --port 8000
```

### 프론트엔드

```bash
cd front/2026_MAR_HACKERTHON
npm install
npm run dev
# → http://localhost:5173 에서 접속
# → /api 요청은 localhost:8000으로 프록시
```

### 환경변수

| 변수 | 위치 | 용도 |
|------|------|------|
| `OPENAI_API_KEY` | `.env` (루트) | 백엔드 — OpenAI API 호출 |
| `VITE_SUPABASE_URL` | 프론트엔드 `.env` | Supabase 프로젝트 URL |
| `VITE_SUPABASE_ANON_KEY` | 프론트엔드 `.env` | Supabase 익명 키 |
