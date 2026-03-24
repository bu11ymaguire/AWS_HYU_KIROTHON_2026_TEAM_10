# HY-Plan TODO

## 🔴 필수 (시간표 추천이 동작하려면 반드시 필요)

- [x] 한양대 2026-1학기 강의시간표 데이터 확보
  - ✅ `lec/hanyang-sugang.csv` — 1,701개 강좌, 82개 학과
  - ✅ `src/course_loader.py` — 한양대 CSV 형식 파서 구현 (시간표, 영어전용/IC-PBL/SMART 플래그)
  - ✅ 기본 경로 `lec/hanyang-sugang.csv` 자동 로드 (환경변수 `COURSES_CSV_PATH`로 오버라이드 가능)
- [x] 강의 데이터 → `Course` 객체 변환 로더 구현 (`src/course_loader.py`)
- [x] 챗봇 시간표 추천 멀티턴 대화 구현
  - 세션 상태 관리 → 학년/학과/이수현황/희망과목 순차 수집 → `ScheduleRecommender.recommend()` 호출
- [x] API에 세션 관리 추가 (session_id 기반 멀티턴 대화 컨텍스트 유지)

## 🟡 중요 (완성도를 위해 필요)

- [x] `_handle_credit_check()`에서 출처 페이지 표시 제거
- [ ] `_handle_schedule_info()` 실제 동작 검증 — `parsed_data.schedule`이 제대로 파싱되는지 확인
- [ ] 프론트엔드에서 시간표 결과를 표(테이블) 형태로 렌더링
  - 현재 ChatInterface는 텍스트만 표시
  - 마크다운 테이블 파싱 또는 커스텀 시간표 컴포넌트 필요
- [x] 에러 시 사용자 친화적 메시지 개선 (API에서 상세 에러 대신 안내 메시지 반환)
- [ ] Gemini API rate limit 대응 — 429 에러 시 자동 재시도 또는 큐잉

## 🟢 개선 (있으면 좋은 것)

- [ ] 졸업사정 조회 기능 연동 (프론트 `GraduationAudit` 컴포넌트와 백엔드 연결)
- [ ] 대화 히스토리 저장 (Supabase 활용 — 프론트에 이미 supabaseClient 있음)
- [ ] "다른 조합 보여줘"로 대안 시간표 제공
- [ ] 폐강 위험 과목 실시간 수강인원 반영
- [ ] HuggingFace 임베딩 deprecation 경고 해결 (`langchain-huggingface` 패키지로 마이그레이션)
- [ ] 프론트 프로덕션 빌드 + 백엔드 static file 서빙 (단일 서버 배포)
