# HY-Plan — 한양대 서울캠퍼스 수강신청 AI 도우미

한양대학교 서울캠퍼스 2026-1학기 학사안내를 기반으로, RAG 학사 규정 Q&A와 규칙 엔진 기반 시간표 추천을 제공하는 AI 챗봇입니다.

## 프로젝트 구조

```
├── src/                  # 백엔드 (Python)
│   ├── main.py           # CLI 엔트리포인트
│   ├── api.py            # FastAPI 서버 (프론트엔드 연동)
│   ├── chatbot.py        # Intent 분류 + 대화 라우팅
│   ├── rag_pipeline.py   # RAG Q&A (Chroma + Gemini)
│   ├── preprocessor.py   # data.md 파싱 및 구조화
│   ├── models.py         # 데이터 모델 (dataclass)
│   ├── course_loader.py  # 강의 CSV 로드
│   ├── schedule_recommender.py  # 시간표 추천 (5개 검증기 통합)
│   ├── credit_validator.py      # 학점 상한/하한 검증
│   ├── conflict_checker.py      # 시간표 충돌 검사
│   ├── prerequisite_checker.py  # 선수-후수 과목 검증
│   ├── cancellation_checker.py  # 폐강 위험 판정
│   ├── equivalent_manager.py    # 동일/대치 교과목 관리
│   └── curriculum_advisor.py    # 교육과정 적용 규칙
│
├── front/                # 프론트엔드 (React + TypeScript + Vite)
│   │                     # 출처: https://github.com/IndianKimchiMan/2026_MAR_HACKERTHON
│   └── README.md
│
├── lec/                  # 강의 데이터 (CSV, gitignore 대상)
│   ├── hanyang-sugang.csv    # 학교 공식 수강편람
│   ├── lectures.csv          # 에브리타임 강의평
│   ├── board-258585.csv      # 에브리타임 게시판
│   └── tips.csv              # 에브리타임 꿀팁 게시판
│
├── data/                 # 벡터 DB 저장소
│   └── chroma_db/        # Chroma 벡터 DB 파일
│
├── tests/                # 테스트 (pytest, 205개)
├── data.md               # 학사안내 원문 (PDF → 텍스트)
├── .env                  # 환경변수 (GOOGLE_API_KEY)
└── requirements.txt      # Python 의존성
```

## 동작 방식

### 1. 초기화 파이프라인

```
data.md 읽기
  → PageParser (페이지 분리)
  → DataParser (6개 영역 구조화: 일정/학점규칙/폐강기준/선수후수/동일대치/교육과정)
  → Chroma 벡터 DB 인덱싱 (800자 청크, 200자 오버랩, 한국어 임베딩)
  → 5개 검증기 초기화
  → ChatBot 생성
```

### 2. Intent 분류 및 처리

사용자 입력을 키워드 매칭 + Gemini LLM으로 분류하여 적절한 핸들러로 라우팅합니다.

| Intent | 예시 질문 | 처리 방식 |
|--------|----------|-----------|
| `SCHEDULE_INFO` | "3학년 수강신청 일정 알려줘" | 구조화 데이터에서 학년별 일정 조회 |
| `SCHEDULE_RECOMMEND` | "시간표 추천해줘" | 멀티턴 대화로 정보 수집 → 시간표 생성 |
| `CREDIT_CHECK` | "최대 몇 학점까지 들을 수 있어?" | RAG 파이프라인 |
| `DROP_CHECK` | "수강포기 기간이 언제야?" | 규칙 기반 응답 |
| `RETAKE_INFO` | "재수강 조건이 뭐야?" | 규칙 기반 응답 |
| `DIFFICULTY_CHECK` | "이 과목 수강신청 난이도 알려줘" | 경쟁률/평가수/별점 기반 산정 |
| `REGULATION_QA` | 기타 학사 규정 질문 | RAG (벡터 검색 → Gemini 답변 생성) |

### 3. 시간표 추천 흐름

멀티턴 대화로 학생 정보를 순차 수집합니다:

```
학년 → 학과 → 이수 과목 → 공강 요일 → 희망 과목
```

수집 완료 후 5단계 검증을 거쳐 시간표를 생성합니다:

1. 학점 상한/하한 검증
2. 시간 충돌 검사
3. 선수-후수 과목 확인
4. 폐강 위험 판정
5. 동일/대치 교과목 확인

결과로 플랜 A(평점 최적)와 플랜 B(경쟁률 안전) 두 가지 시간표를 제공합니다.

### 4. RAG Q&A

```
질문 → 한국어 임베딩 (ko-sroberta-multitask)
     → Chroma 유사도 검색 (Top-5, threshold ≥ 0.15)
     → 컨텍스트 + 질문을 Gemini에 전달
     → 답변 생성 (근거 없으면 "해당 정보를 찾을 수 없습니다")
```

## 실행 방법

### 백엔드 (CLI)

```bash
pip install -r requirements.txt
# .env 파일에 GOOGLE_API_KEY 설정
python -m src.main
```

### 백엔드 (API 서버)

```bash
uvicorn src.api:app --port 8000
```

### 프론트엔드

```bash
cd front/2026_MAR_HACKERTHON
npm install
npm run dev
# http://localhost:5173 → /api 요청은 localhost:8000으로 프록시
```

## 환경변수

| 변수 | 용도 |
|------|------|
| `GOOGLE_API_KEY` | Google Gemini API 키 (Google AI Studio에서 무료 발급) |

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | Python, FastAPI, LangChain |
| LLM | Google Gemini 2.5 Flash |
| 임베딩 | HuggingFace ko-sroberta-multitask (로컬) |
| 벡터 DB | Chroma (로컬) |
| 프론트엔드 | React, TypeScript, Vite, TailwindCSS |
| 테스트 | pytest, Hypothesis |
