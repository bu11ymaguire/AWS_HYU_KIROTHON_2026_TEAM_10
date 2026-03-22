# 한양대 서울캠퍼스 시간표 추천 챗봇 — 구현 요약

## 프로젝트 개요

한양대학교 서울캠퍼스 2026-1학기 학사안내(`data.md`) 원문을 기반으로, RAG 기반 학사 규정 Q&A와 규칙 엔진 기반 시간표 추천을 제공하는 Python CLI 챗봇이다.

실행: `python src/main.py` (`.env`에 `OPENAI_API_KEY` 필요)

---

## 모듈 구성 및 구현 로직

### 1. 데이터 모델 (`src/models.py`)

17개 dataclass 정의:

| 분류 | 클래스 |
|------|--------|
| 입력 | `StudentInfo`, `Course`, `TimeSlot`, `Page`, `ParsedData` |
| 규칙 | `PrerequisiteRule`, `EquivalentCourse` |
| 전처리 | `PreprocessorWarning` |
| 검증 결과 | `CreditValidationResult`, `ConflictResult`, `PrerequisiteWarning`, `CancellationResult`, `EquivalentAdvice` |
| 기타 | `DepartmentInfo`, `ChunkSource`, `RAGResponse`, `ScheduleResult` |

---

### 2. 전처리 모듈 (`src/preprocessor.py`)

`data.md` 원문을 구조화된 데이터로 변환한다.

- **PageParser**: `--- 페이지 N ---` 구분자로 텍스트를 `Page` 리스트로 분리
- **TableNormalizer**: 깨진 표 형식(2+공백/탭 구분)을 `[{헤더: 값}]` dict 리스트로 정규화. 열 수 불일치 시 `PreprocessorWarning` 생성
- **DataParser**: 페이지를 키워드 매칭으로 6개 영역으로 분류 후 구조화
  - `schedule` — 수강신청/수강정정/수강포기 일정 (학년별 날짜·시간)
  - `credit_rules` — 학점 상한/하한 규칙 (2025이전/2026신입생 분기, 추가학점 규칙)
  - `cancel_rules` — 폐강 기준 (일반기준 7개 구간 + 별도기준 면제 11개 대상)
  - `prerequisites` — 선수-후수 관계 (영어기초학력평가 면제 포함)
  - `equivalent_courses` — 동일 교과목 12쌍 + 대치 교과목 25쌍
  - `curriculum_rules` — 4년 단위 교육과정 적용 원칙, 2026년 특례, 학적변동 규칙

---

### 3. 학점 검증기 (`src/credit_validator.py`)

학년·학기·상태에 따른 수강신청 학점 범위를 검증한다.

- **최소학점**: 일반 10 / 4-2 졸업예정 3 / 9학기 이상(학업연장) 1
- **최대학점 (기본)**: 일반 20 / 2026 신입생 3학년 이상(건축학부 제외) 18
- **추가학점**:
  - 커리어개발Ⅰ/Ⅱ, 사회봉사, 군사학 → 최대 +2학점
  - 다전공자 타전공 일반선택 → 최대 +3학점
- `validate()` → 범위 위반 시 `is_valid=False` + 경고 메시지

---

### 4. 시간표 충돌 검증기 (`src/conflict_checker.py`)

희망 과목 간 시간 겹침을 검사한다.

- `_is_overlapping()`: 동일 요일 + `start_a < end_b AND start_b < end_a`
- `check_all_pairs()`: 모든 과목 쌍 × 모든 TimeSlot 조합 비교
- `find_conflict_free_combinations()`: 백트래킹으로 충돌 없는 모든 부분집합 탐색
- `suggest_minimal_removal()`: 그리디 방식으로 충돌 최다 관여 과목부터 제거

---

### 5. 선수-후수 검증기 (`src/prerequisite_checker.py`)

후수과목 신청 시 선수과목 이수 여부를 확인한다.

- 규칙 리스트(`PrerequisiteRule`)를 순회하며 후수과목이 희망 목록에 있고 선수과목이 이수 목록에 없으면 경고
- **면제 규칙**: 영어기초학력평가 A등급 → 기초+전문학술영어 면제, B등급 → 기초학술영어 면제

---

### 6. 폐강 판정기 (`src/cancellation_checker.py`)

수강인원 기준으로 폐강 위험 여부를 판정한다.

- **별도기준 (우선 적용)**: 커리어개발, 캡스톤디자인, 사회봉사, 교직, ROTC 등 11개 대상 → 항상 폐강 위험 없음
- **일반기준**:
  - 영어전용/IC-PBL → 8명 미만 시 위험
  - 전공심화 스마트교과 → 6명 미만 시 위험
  - 재학인원 25명 이상 → 수강인원 10명 미만 시 위험
  - 재학인원 15~24명 → 수강인원 < 재학인원의 40% 시 위험
  - 재학인원 14명 이하 → 수강인원 6명 미만 시 위험

---

### 7. 동일/대치 교과목 관리기 (`src/equivalent_manager.py`)

이수 과목과 희망 과목 간 동일/대치 관계를 확인한다.

- **동일 교과목** → "재수강으로만 신청 가능"
- **대치 교과목** → "재수강 또는 일반수강 선택 가능"
- 관계 없음 → `None` 반환

---

### 8. 교육과정 적용 규칙 (`src/curriculum_advisor.py`)

학번(입학년도)과 학년으로 적용 교육과정을 결정한다.

- **4년 단위 사이클**: 2020-2023, 2024-2027
- **2026학년도 특례**: 1~3학년 → 2024-2027 / 4~5학년 건축학부 → 2020-2023
- `get_curriculum_changes()`: 휴·복학 이력에 따른 교육과정 변동 안내

---

### 9. RAG 파이프라인 (`src/rag_pipeline.py`)

LangChain + Chroma + OpenAI 기반 학사 규정 Q&A 시스템이다.

- **인덱싱**: 페이지 → `RecursiveCharacterTextSplitter`(800자/200자 오버랩) → 청크별 임베딩(`text-embedding-3-small`) → Chroma 벡터 DB 저장 (페이지 번호 메타데이터 포함)
- **질의**: 질문 임베딩 → top-5 유사도 검색(threshold ≥ 0.3) → 시스템 프롬프트 + 컨텍스트 구성 → `gpt-4o` 답변 생성
- 근거 없는 질문 → "해당 정보를 찾을 수 없습니다" 응답

---

### 10. 시간표 추천기 (`src/schedule_recommender.py`)

5개 검증기를 통합하여 추천 시간표를 생성한다.

- `recommend()` 검증 순서: 학점 → 충돌 → 선수-후수 → 폐강 → 동일/대치
- 시간표를 요일(월~금) × 교시(1~15) 2D 배열로 생성
- 폐강 위험 과목에 `[폐강 위험]`, 선수과목 미이수 과목에 `[선수과목 미이수]` 접미사 추가
- `check_drop_eligibility()`: 수강포기 가능 여부 검증 (잔여학점 ≥ 최소학점, 최대 2과목, 학사학위취득유예자 불가)

---

### 11. 의도 분류기 및 CLI 챗봇 (`src/chatbot.py`)

사용자 입력을 분류하고 적절한 핸들러로 라우팅한다.

- **Intent 분류** (키워드 매칭, 긴 키워드 우선):
  - `SCHEDULE_INFO` — "수강신청 일정", "언제 신청" 등
  - `SCHEDULE_RECOMMEND` — "시간표 추천", "시간표 짜" 등
  - `CREDIT_CHECK` — "학점", "최대 학점" 등
  - `DROP_CHECK` — "수강포기", "드롭" 등
  - `RETAKE_INFO` — "재수강", "성적상승" 등
  - `REGULATION_QA` — 위 어디에도 매칭되지 않으면 RAG Q&A로 폴백

- **핸들러**:
  - 학사 규정 Q&A → RAG 파이프라인 호출, 출처 페이지 번호 표시
  - 수강신청 일정 → 텍스트에서 학년 추출 후 해당 학년 일정 포맷팅
  - 시간표 추천 → 필수 정보(학번/학년/학과/이수현황/희망과목) 수집 안내
  - 수강포기 → 기간, 최대 과목 수, 조건, 제한 대상 안내
  - 성적상승재수강 → C+ 이하 대상, A0 제한, 2025학번부터 2회 제한 안내

- **CLI**: `rich` 테이블 출력, `.env` API 키 검증, `Ctrl+C` 정상 종료

---

### 12. 엔트리포인트 (`src/main.py`)

전체 파이프라인을 연결하여 실행한다.

```
data.md 읽기 → PageParser → DataParser → ParsedData
                                ↓
                         RAGPipeline.index()
                                ↓
              CreditValidator / ConflictChecker / PrerequisiteChecker
              CancellationChecker / EquivalentManager 초기화
                                ↓
                       ScheduleRecommender 생성
                                ↓
                         ChatBot.run() (CLI)
```

---

## 테스트

총 205개 테스트 (pytest), 10개 테스트 파일. 모든 테스트 통과.

| 테스트 파일 | 대상 모듈 |
|------------|-----------|
| `test_preprocessor.py` | PageParser, TableNormalizer, DataParser |
| `test_credit_validator.py` | CreditValidator |
| `test_conflict_checker.py` | ConflictChecker |
| `test_prerequisite_checker.py` | PrerequisiteChecker |
| `test_cancellation_checker.py` | CancellationChecker |
| `test_equivalent_manager.py` | EquivalentManager |
| `test_curriculum_advisor.py` | CurriculumAdvisor |
| `test_rag_pipeline.py` | RAGPipeline (mocked) |
| `test_schedule_recommender.py` | ScheduleRecommender |
| `test_chatbot.py` | IntentRouter, ChatBot |
