# 프로젝트 피드백 — 한양대 수강신청 AI Agent

## 1. Spec과 실제 구현의 기술 스택 불일치

Spec(d2.md)에서는 AWS Lambda (Node.js 18) + TypeScript + CDK + DynamoDB + OpenSearch Serverless + Bedrock을 설계했지만, 실제 구현은 Python FastAPI + Chroma (로컬 벡터 DB) + Google Gemini + HuggingFace 임베딩으로 완전히 다른 스택이 되었다.

이 자체가 나쁜 건 아니다. 해커톤에서 AWS 인프라 세팅에 시간을 쓰는 건 리스크가 크고, Python + Gemini 조합이 훨씬 빠르게 돌아가는 프로토타입을 만들 수 있다. 문제는 Spec을 바꾸지 않고 코드만 바꿨다는 점이다. Spec과 코드가 따로 놀면 나중에 어떤 문서를 믿어야 하는지 혼란이 생긴다.

**개선안:** 기술 스택 변경 시점에 d2.md를 간단히라도 업데이트했으면 좋았다. "Lambda → FastAPI, Bedrock → Gemini, OpenSearch → Chroma" 정도만 메모해도 충분하다.

## 2. 졸업사정 이미지 분석 기능 미구현

r2.md 요구사항 2번(졸업사정 이미지 분석)은 핵심 기능 중 하나였는데, 실제 코드에는 Vision 분석 모듈이 없다. GraduationAudit 컴포넌트가 프론트에 존재하지만 백엔드에 이미지 분석 엔드포인트가 없고, API는 텍스트 기반 `/api/chat` 하나뿐이다.

Spec에서 P1(필수)으로 분류한 기능이 빠진 건 아쉽다. 이미지 분석이 없으면 "졸업사정 기반 강의 추천"이라는 핵심 차별점이 사라진다.

## 3. 강의 추천 로직의 방향 전환

Spec에서는 "졸업사정 분석 → 미이수 영역 파악 → Bedrock으로 최적 강의 3개 추천 (전공 3 + 교양 3)"을 설계했다. 실제 구현은 멀티턴 대화 기반 시간표 추천기로 바뀌었다. 학년/학과/이수과목/희망과목을 순차 수집해서 플랜 A(평점 최적)/B(경쟁률 안전) 시간표를 생성하는 방식이다.

방향 자체는 나쁘지 않고 오히려 실용적이다. 하지만 "AI가 알아서 추천"이 아니라 "사용자가 희망 과목을 직접 입력"하는 구조라서, Spec이 약속한 "수강신청 시간을 절약하고 최적의 강의를 선택"이라는 가치와는 거리가 있다.

## 4. Intent 분류기: 설계 vs 구현

Spec에서는 7개 Intent(GRADUATION, COURSE_RECOMMEND, SCHEDULE_INFO, CREDIT_CHECK, DROP_CHECK, PREREQUISITE, REGULATION_QA)를 정의했다. 실제 구현은 8개 Intent(REGULATION_QA, SCHEDULE_RECOMMEND, SCHEDULE_INFO, CREDIT_CHECK, DROP_CHECK, RETAKE_INFO, FREE_DAY_SCHEDULE, DIFFICULTY_CHECK)로, GRADUATION/COURSE_RECOMMEND/PREREQUISITE가 빠지고 RETAKE_INFO/FREE_DAY_SCHEDULE/DIFFICULTY_CHECK가 추가되었다.

기능 범위가 바뀌면서 Intent도 바뀐 건 자연스럽지만, 이 변경이 Spec에 반영되지 않아서 문서와 코드 사이에 괴리가 크다.

## 5. RAG 파이프라인: 잘 구현된 부분

RAG는 Spec의 설계 의도를 비교적 잘 따랐다. 800자 청크 분리, 코사인 유사도 Top-5 검색, LLM 답변 생성 흐름이 d2.md 설계와 일치한다. 다만 Bedrock Titan Embeddings 대신 로컬 HuggingFace 임베딩(ko-sroberta-multitask)을 쓴 건 현실적인 선택이었고, OpenSearch 대신 Chroma를 쓴 것도 로컬 개발에 적합했다.

아쉬운 점은 RAG 응답에 출처(sources)를 반환하도록 백엔드에서 구현했지만, 프론트엔드 ChatInterface에서는 sources를 표시하지 않는다는 것이다. API 응답 스키마에도 sources 필드가 없다.

## 6. 프론트엔드: 채팅 UI 중심으로의 전환

Spec에서는 입력 폼(전공/학년/관심분야/이미지 업로드) → 결과 카드(추천 강의 3개 + 졸업 진행 바) 구조를 설계했다. 실제 구현은 Gemini 스타일 채팅 인터페이스로, 자유 텍스트 입력 → 마크다운 응답 표시 구조다.

채팅 UI가 더 범용적이고 확장성이 좋긴 하지만, 시간표 결과가 마크다운 테이블로만 표시되어 시각적 임팩트가 약하다. Spec에서 설계한 시간표 격자 시각화, 졸업 영역별 진행 바, 난이도 뱃지 같은 시각 요소가 빠져서 데모 시 아쉬울 수 있다.

## 7. 테스트 전략

t2.md에서 Property-Based Testing(fast-check)을 포함한 20개 Property를 정의하고 테스트 파일 구조까지 설계했다. 실제 tests/ 폴더에 테스트가 있긴 하지만 Python pytest 기반이고, Spec에서 설계한 Property 테스트 대부분은 구현되지 않았을 가능성이 높다(TypeScript fast-check 기반으로 설계되었으므로).

해커톤에서 테스트를 완벽히 갖추기는 어렵지만, 최소한 핵심 로직(시간표 충돌 검사, 학점 검증)에 대한 단위 테스트는 있으면 좋았다.

## 8. 수강신청 난이도 분석: 잘 구현된 부분

r2.md US-04에서 정의한 난이도 계산 공식(경쟁률 40% + 평가수 30% + 별점 30%)이 schedule_recommender.py의 `analyze_difficulty` 메서드에 거의 그대로 구현되어 있다. min-max 정규화, 4단계 레벨 분류, 팁 메시지까지 잘 들어가 있다. Spec → 코드 일치도가 가장 높은 부분이다.

## 9. 세션 관리와 멀티턴 대화

Spec에는 없었지만 실제 구현에서 추가된 좋은 기능이다. ScheduleSession 상태 머신으로 학년 → 학과 → 이수과목 → 공강 → 희망과목을 순차 수집하는 흐름이 자연스럽다. LLM 기반 학과명/과목명 fuzzy matching도 실용적이다.

다만 세션이 메모리에만 저장되어 서버 재시작 시 날아간다. 해커톤 데모에서는 문제없지만, 실서비스라면 Redis나 DynamoDB 세션 스토어가 필요하다.

## 종합

Spec 문서(r2.md, d2.md, t2.md)의 퀄리티 자체는 높았다. 요구사항 → 설계 → 태스크 분해 → Property 정의까지 체계적이었다. 문제는 해커톤 진행 중 기술 스택과 기능 범위가 크게 바뀌면서 Spec이 업데이트되지 않았다는 점이다.

"d2.md, r2.md, t2.md만 갖고 Spec을 진행했으면 결과가 더 잘 나왔을까?"에 대한 답은: 구조적으로는 더 깔끔했겠지만, AWS 인프라 세팅 시간을 고려하면 현실적으로 완성도가 더 낮았을 수 있다. Python + Gemini로 빠르게 전환한 판단은 맞았고, 다만 그 시점에 Spec을 같이 업데이트했으면 "로직이 꼬인" 느낌이 훨씬 덜했을 것이다.
