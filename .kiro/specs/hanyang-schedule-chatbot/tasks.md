# 구현 계획: 한양대 서울캠퍼스 시간표 추천 챗봇

## 개요

data.md 학사안내 원문을 기반으로 RAG 기반 학사 규정 Q&A, 규칙 엔진 기반 검증, 시간표 추천 기능을 제공하는 Python CLI 챗봇을 구현한다. 전처리/파싱 → 규칙 엔진 모듈 → RAG 파이프라인 → 시간표 추천기 → CLI 인터페이스 순서로 점진적으로 구현하며, 각 단계에서 Property-Based 테스트로 정확성을 검증한다.

## 태스크

- [x] 1. 프로젝트 구조 설정 및 데이터 모델 정의
  - [x] 1.1 프로젝트 디렉토리 구조 및 의존성 설정
    - `pyproject.toml` 또는 `requirements.txt` 생성 (langchain, chromadb, openai, rich, python-dotenv, hypothesis, pytest)
    - `.env.example` 파일 생성 (OPENAI_API_KEY 등), `.gitignore`에 `.env` 추가
    - 프로젝트 디렉토리 구조 생성: `src/`, `tests/`, `data/`
    - _요구사항: 10.2_

  - [x] 1.2 핵심 데이터 모델 정의 (`src/models.py`)
    - `StudentInfo`, `Course`, `TimeSlot`, `Page`, `ParsedData` dataclass 정의
    - `PrerequisiteRule`, `EquivalentCourse`, `PreprocessorWarning` dataclass 정의
    - 각 검증 결과 dataclass 정의: `CreditValidationResult`, `ConflictResult`, `PrerequisiteWarning`, `CancellationResult`, `EquivalentAdvice`
    - _요구사항: 1.3, 2.1, 3.1, 4.1, 5.1, 6.1_

- [x] 2. 학사안내 데이터 전처리 및 파싱 모듈 구현
  - [x] 2.1 페이지 파서 및 표 정규화기 구현 (`src/preprocessor.py`)
    - `PageParser.parse_pages()`: "--- 페이지 N ---" 구분자 기반 파싱, 각 Page에 page_number 메타데이터 부여
    - `TableNormalizer.normalize()`: 깨진 행/열 구조를 일관된 키-값 dict 리스트로 변환
    - 인식 불가 데이터 발견 시 `PreprocessorWarning` 생성 (페이지 번호, 라인 번호 포함)
    - _요구사항: 1.1, 1.2, 1.5_

  - [x] 2.2 영역별 데이터 파서 구현 (`src/preprocessor.py`)
    - `DataParser.parse()`: 6개 영역(schedule, credit_rules, cancel_rules, prerequisites, equivalent_courses, curriculum_rules)으로 분리
    - 각 영역별 JSON 스키마에 맞는 구조화 데이터 생성
    - 파싱 결과를 JSON 파일로 저장하는 기능 구현
    - _요구사항: 1.3, 1.4_

  - [ ]* 2.3 전처리 모듈 Property 테스트 작성 (`tests/test_preprocessor.py`)
    - **Property 1: 파싱 멱등성** — 동일 입력 두 번 파싱 시 동일 결과 보장
    - **검증 대상: 요구사항 1.4**
  
  - [ ]* 2.4 페이지 구분자 파싱 Property 테스트 작성 (`tests/test_preprocessor.py`)
    - **Property 2: 페이지 구분자 파싱 정확성** — 청크 수와 구분자 수 일치, 페이지 번호 정확성
    - **검증 대상: 요구사항 1.1**

  - [ ]* 2.5 인식 불가 데이터 경고 Property 테스트 작성 (`tests/test_preprocessor.py`)
    - **Property 3: 인식 불가 데이터 경고 포함 정보** — 경고에 페이지 번호, 라인 번호 포함
    - **검증 대상: 요구사항 1.5**

  - [ ]* 2.6 전처리 모듈 단위 테스트 작성 (`tests/test_preprocessor.py`)
    - 깨진 표 형식 정규화 예시 테스트 (요구사항 1.2)
    - 6개 영역 분리 확인 테스트 (요구사항 1.3)

- [x] 3. 체크포인트 — 전처리 모듈 검증
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 문의한다.

- [x] 4. 학점 검증기 구현
  - [x] 4.1 학점 검증기 핵심 로직 구현 (`src/credit_validator.py`)
    - `CreditValidator.__init__()`: credit_rules JSON 로드
    - `CreditValidator._calculate_min_credits()`: 학기별 최소학점 반환 (1-1~4-1: 10, 4-2 졸업예정: 3, 9학기 이상: 1)
    - `CreditValidator._calculate_max_credits()`: 기본 최대학점 + 추가학점 계산
    - 2026 신입생 규칙 분기 처리 (1~2학년: max 20, 3학년 이상 건축학부 제외: max 18)
    - 추가학점 계산: 커리어개발/사회봉사/군사학 최대 2학점, 다전공 타전공 일반선택 최대 3학점
    - `CreditValidator.validate()`: 총 학점 범위 검증 및 CreditValidationResult 반환
    - _요구사항: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 4.2 학점 범위 적용 Property 테스트 작성 (`tests/test_credit_validator.py`)
    - **Property 4: 학기/상태별 학점 범위 적용** — 학년, 학기, 상태 플래그 조합에 따른 올바른 min/max 반환
    - **검증 대상: 요구사항 2.1, 2.2, 2.3, 2.6, 2.7**

  - [ ]* 4.3 추가학점 상한 Property 테스트 작성 (`tests/test_credit_validator.py`)
    - **Property 5: 추가학점 상한 준수** — 커리어개발 등 최대 2학점, 다전공 타전공 최대 3학점
    - **검증 대상: 요구사항 2.4, 2.5**

  - [ ]* 4.4 학점 위반 경고 Property 테스트 작성 (`tests/test_credit_validator.py`)
    - **Property 6: 학점 범위 위반 경고 생성** — 범위 위반 시 is_valid=False, warnings에 메시지 포함
    - **검증 대상: 요구사항 2.8**

- [x] 5. 시간표 충돌 검증기 구현
  - [x] 5.1 시간표 충돌 검증기 핵심 로직 구현 (`src/conflict_checker.py`)
    - `ConflictChecker._is_overlapping()`: 동일 요일 + start_a < end_b AND start_b < end_a 판정
    - `ConflictChecker.check_all_pairs()`: 모든 과목 쌍 시간 충돌 검사
    - `ConflictChecker.find_conflict_free_combinations()`: 백트래킹 기반 충돌 없는 조합 탐색
    - `ConflictChecker.suggest_minimal_removal()`: 충돌 최소화를 위한 제외 과목 안내
    - _요구사항: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 5.2 시간 충돌 판정 Property 테스트 작성 (`tests/test_conflict_checker.py`)
    - **Property 7: 시간 충돌 판정 정확성** — 랜덤 TimeSlot 쌍에 대해 겹침 조건 정확 판정
    - **검증 대상: 요구사항 3.1, 3.2**

  - [ ]* 5.3 시간표 충돌 검증기 단위 테스트 작성 (`tests/test_conflict_checker.py`)
    - 충돌 없는 조합 표 형태 출력 테스트 (요구사항 3.3)
    - 모든 조합 충돌 시 대안 제시 테스트 (요구사항 3.4)

- [x] 6. 선수-후수 검증기 구현
  - [x] 6.1 선수-후수 검증기 핵심 로직 구현 (`src/prerequisite_checker.py`)
    - `PrerequisiteChecker.__init__()`: 선수-후수 규칙 리스트 로드
    - `PrerequisiteChecker.check()`: 희망 과목 중 선수과목 미이수 항목 경고 생성
    - 영어기초학력평가 A/B등급 면제 규칙 처리
    - _요구사항: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 6.2 선수과목 미이수 경고 Property 테스트 작성 (`tests/test_prerequisite_checker.py`)
    - **Property 8: 선수과목 미이수 경고** — 후수과목 신청 시 선수과목 미이수면 경고 포함
    - **검증 대상: 요구사항 4.2**

  - [ ]* 6.3 선수-후수 검증기 단위 테스트 작성 (`tests/test_prerequisite_checker.py`)
    - A등급/B등급 면제 규칙 테스트 (요구사항 4.3, 4.4)
    - 선수-후수 관계 데이터 구조 테스트 (요구사항 4.1)

- [x] 7. 체크포인트 — 규칙 엔진 핵심 모듈 검증
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 문의한다.

- [x] 8. 폐강 판정기 구현
  - [x] 8.1 폐강 판정기 핵심 로직 구현 (`src/cancellation_checker.py`)
    - `CancellationChecker._is_special_exempt()`: 별도기준 대상 여부 확인
    - `CancellationChecker._apply_general_rule()`: 재학인원 구간별 폐강 기준 적용
    - `CancellationChecker.check()`: 별도기준 우선 적용 후 일반기준 판정
    - 영어전용/제2외국어전용/IC-PBL 별도 기준 처리
    - _요구사항: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 8.2 폐강 일반기준 Property 테스트 작성 (`tests/test_cancellation_checker.py`)
    - **Property 9: 폐강 판정 일반기준 적용** — 재학인원 구간별 올바른 폐강 기준 적용
    - **검증 대상: 요구사항 5.1, 5.2, 5.3, 5.4**

  - [ ]* 8.3 폐강 별도기준 우선 적용 Property 테스트 작성 (`tests/test_cancellation_checker.py`)
    - **Property 10: 폐강 판정 별도기준 우선 적용** — 별도기준 대상 과목은 항상 폐강 위험 False
    - **검증 대상: 요구사항 5.5, 5.6**

- [x] 9. 동일/대치 교과목 관리기 구현
  - [x] 9.1 동일/대치 교과목 관리기 핵심 로직 구현 (`src/equivalent_manager.py`)
    - `EquivalentManager.__init__()`: 동일/대치 교과목 리스트 로드
    - `EquivalentManager.check()`: 동일 교과목 → "재수강으로만 신청 가능", 대치 교과목 → "재수강 또는 일반수강 선택 가능", 관계 없음 → None
    - _요구사항: 6.1, 6.2, 6.3_

  - [ ]* 9.2 동일/대치 안내 Property 테스트 작성 (`tests/test_equivalent_manager.py`)
    - **Property 11: 동일/대치 교과목 안내 정확성** — 관계 유형에 따른 올바른 안내 메시지 반환
    - **검증 대상: 요구사항 6.2, 6.3**

  - [ ]* 9.3 동일/대치 교과목 단위 테스트 작성 (`tests/test_equivalent_manager.py`)
    - 구조화 데이터 관리 확인 테스트 (요구사항 6.1)

- [x] 10. 교육과정 적용 규칙 모듈 구현
  - [x] 10.1 교육과정 적용 규칙 핵심 로직 구현 (`src/curriculum_advisor.py`)
    - `CurriculumAdvisor.get_curriculum()`: 학번/학년 기반 적용 교육과정 반환
    - `CurriculumAdvisor.get_curriculum_changes()`: 휴·복학 이력에 따른 교육과정 변동 사항 안내
    - _요구사항: 7.1, 7.2, 7.3_

  - [ ]* 10.2 교육과정 적용 규칙 Property 테스트 작성 (`tests/test_curriculum_advisor.py`)
    - **Property 12: 교육과정 적용 규칙 정확성** — 학번/학년에 따른 올바른 교육과정 반환
    - **검증 대상: 요구사항 7.1, 7.3**

  - [ ]* 10.3 교육과정 단위 테스트 작성 (`tests/test_curriculum_advisor.py`)
    - 휴·복학 이력에 따른 변동 시나리오 테스트 (요구사항 7.2)

- [x] 11. 체크포인트 — 전체 규칙 엔진 모듈 검증
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 문의한다.

- [x] 12. RAG 파이프라인 구축
  - [x] 12.1 RAG 파이프라인 핵심 구현 (`src/rag_pipeline.py`)
    - `RAGPipeline.__init__()`: Chroma 벡터 DB 연결, LLM 모델 설정
    - `RAGPipeline.index()`: 페이지를 의미 단위 청크로 분할 → 임베딩 생성 → Chroma 저장 (페이지 번호 메타데이터 포함)
    - `RAGPipeline.query()`: 질문 임베딩 → top-k 유사도 검색 → LLM 프롬프트 구성 → 답변 생성
    - `RAGResponse` 반환: 답변 텍스트, 출처(페이지 번호), 근거 존재 여부
    - 근거 없는 질문에 대해 "해당 정보를 찾을 수 없습니다" 응답 처리
    - LangChain 프레임워크 기반 구현
    - _요구사항: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 12.2 청크 메타데이터 보존 Property 테스트 작성 (`tests/test_rag_pipeline.py`)
    - **Property 13: 청크 메타데이터 보존** — 벡터 DB 저장 청크에 원본 페이지 번호 포함, RAG 응답 sources에 페이지 번호 포함
    - **검증 대상: 요구사항 8.1, 8.3**

- [x] 13. 시간표 추천기 구현
  - [x] 13.1 시간표 추천기 핵심 로직 구현 (`src/schedule_recommender.py`)
    - `ScheduleRecommender.__init__()`: 학점 검증기, 충돌 검증기, 선수-후수 검증기, 폐강 판정기, 동일/대치 관리기 주입
    - `ScheduleRecommender.recommend()`: 통합 검증 수행 (학점 → 충돌 → 선수-후수 → 폐강 → 동일/대치) 후 ScheduleResult 반환
    - 추천 시간표를 요일×교시 2D 배열로 생성
    - 폐강 위험 과목에 "폐강 위험" 경고 추가
    - 선수과목 미이수 과목에 "선수과목 미이수 경고" 추가
    - _요구사항: 9.1, 9.2, 9.3, 9.4_

  - [x] 13.2 수강포기 가능 여부 검증 로직 구현 (`src/schedule_recommender.py`)
    - 수강포기 후 잔여학점 ≥ 최소학점 검증
    - 최대 2과목 제한 검증
    - 학사학위취득유예자 포기 불가 검증
    - _요구사항: 9.5_

  - [ ]* 13.3 통합 검증 수행 Property 테스트 작성 (`tests/test_schedule_recommender.py`)
    - **Property 14: 시간표 추천 통합 검증 수행** — 학점, 충돌, 선수-후수, 폐강 검증 모두 수행 확인
    - **검증 대상: 요구사항 9.1**

  - [ ]* 13.4 시간표 경고 표시 Property 테스트 작성 (`tests/test_schedule_recommender.py`)
    - **Property 15: 시간표 경고 표시 완전성** — 폐강 위험/선수과목 미이수 과목 포함 시 warnings에 경고 포함
    - **검증 대상: 요구사항 9.3, 9.4**

  - [ ]* 13.5 수강포기 검증 Property 테스트 작성 (`tests/test_schedule_recommender.py`)
    - **Property 16: 수강포기 가능 여부 검증** — 잔여학점 미달/2과목 초과/유예자 시 포기 불가 판정
    - **검증 대상: 요구사항 9.5**

- [x] 14. 체크포인트 — RAG 파이프라인 및 시간표 추천기 검증
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 문의한다.

- [x] 15. 의도 분류기 및 CLI 인터페이스 구현
  - [x] 15.1 의도 분류기 구현 (`src/chatbot.py`)
    - `Intent` Enum 정의: REGULATION_QA, SCHEDULE_RECOMMEND, SCHEDULE_INFO, CREDIT_CHECK, DROP_CHECK, RETAKE_INFO
    - `IntentRouter.classify()`: 사용자 입력의 의도를 분류 (키워드 기반 + LLM 폴백)
    - 의도 분류 실패 시 기본적으로 RAG Q&A로 처리
    - _요구사항: 10.1, 10.3_

  - [x] 15.2 ChatBot 메인 루프 및 핸들러 구현 (`src/chatbot.py`)
    - `ChatBot.__init__()`: RAG 파이프라인, 시간표 추천기, 각 검증기 주입
    - `ChatBot.handle_input()`: 의도 분류 → 적절한 핸들러 호출 → 응답 반환
    - `ChatBot.run()`: CLI 메인 루프 (입력 → 처리 → rich 테이블 출력)
    - 시간표 추천 시 필수 정보(학번, 학년, 학과, 이수 현황, 희망 과목) 순차 수집
    - 수강신청 일정 조회 핸들러 구현 (학년별 날짜/시간 안내)
    - 성적상승재수강 안내 핸들러 구현 (C+이하 대상, A0 제한, 2025학번 2회 제한)
    - 빈 입력 처리, 키보드 인터럽트(Ctrl+C) 정상 종료 처리
    - .env 파일 검증 (API 키 미설정 시 안내 메시지 출력 후 종료)
    - _요구사항: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 15.3 수강신청 일정 조회 Property 테스트 작성 (`tests/test_chatbot.py`)
    - **Property 17: 수강신청 일정 조회 정확성** — 유효한 학년(1~5)에 대해 빈 결과 없이 날짜/시간 정보 포함
    - **검증 대상: 요구사항 10.5**

  - [ ]* 15.4 CLI 인터페이스 단위 테스트 작성 (`tests/test_chatbot.py`)
    - 의도 분류 테스트 (학사 규정 질문, 시간표 추천 요청 등)
    - 성적상승재수강 규칙 안내 테스트 (요구사항 10.6)

- [x] 16. 전체 통합 및 연결
  - [x] 16.1 모듈 간 통합 및 엔트리포인트 구현 (`src/main.py`)
    - data.md 전처리 → 구조화 JSON 생성 → 벡터 DB 인덱싱 → 각 검증기 초기화 → ChatBot 인스턴스 생성 → CLI 실행
    - 모든 모듈을 연결하여 end-to-end 동작 확인
    - _요구사항: 1.1~10.6 전체_

  - [ ]* 16.2 통합 테스트 작성
    - 학사 규정 질문 → RAG 응답 흐름 테스트
    - 시간표 추천 요청 → 통합 검증 → 결과 출력 흐름 테스트
    - _요구사항: 9.1, 10.3, 10.4_

- [x] 17. 최종 체크포인트 — 전체 시스템 검증
  - 모든 테스트가 통과하는지 확인하고, 질문이 있으면 사용자에게 문의한다.

## 참고사항

- `*` 표시된 태스크는 선택사항이며, 빠른 MVP를 위해 건너뛸 수 있습니다
- 각 태스크는 특정 요구사항을 참조하여 추적 가능합니다
- 체크포인트에서 점진적 검증을 수행합니다
- Property 테스트는 Hypothesis 라이브러리를 사용하여 보편적 정확성 속성을 검증합니다
- 단위 테스트는 특정 예시와 엣지 케이스를 검증합니다
