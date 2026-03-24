"""강의 데이터 로더 모듈.

CSV/JSON 파일 또는 샘플 데이터에서 Course 객체 리스트를 생성한다.
한양대 수강신청 CSV(hanyang-sugang.csv) 형식을 기본 지원한다.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import time
from pathlib import Path

from src.models import Course, TimeSlot


def _parse_time(t: str) -> time:
    """'HH:MM' 형식 문자열을 time 객체로 변환. 24:00은 23:59로 처리."""
    parts = t.strip().split(":")
    h, m = int(parts[0]), int(parts[1])
    if h >= 24:
        h, m = 23, 59
    return time(h, m)


def _parse_time_slots(raw: str) -> list[TimeSlot]:
    """한양대 수업시간 형식을 TimeSlot 리스트로 변환.

    지원 형식:
      - '수(09:00-10:30)수(10:30-12:00)'  (한양대 수강신청 CSV)
      - '월10:00~12:00,수10:00~12:00'      (레거시/테스트용)
    '시간미지정강좌' 등은 빈 리스트를 반환한다.
    """
    slots: list[TimeSlot] = []
    if not raw or not raw.strip():
        return slots

    # 한양대 형식: 요일(HH:MM-HH:MM) 패턴이 연속
    hanyang_pattern = re.findall(
        r"([월화수목금토일])\((\d{1,2}:\d{2})-(\d{1,2}:\d{2})\)", raw
    )
    if hanyang_pattern:
        for day, start_str, end_str in hanyang_pattern:
            slots.append(TimeSlot(
                day=day,
                start_time=_parse_time(start_str),
                end_time=_parse_time(end_str),
            ))
        return slots

    # 레거시 형식: 콤마 구분, 요일HH:MM~HH:MM
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.match(
            r"([월화수목금토일])\s*(\d{1,2}:\d{2})\s*[~\-]\s*(\d{1,2}:\d{2})", part
        )
        if match:
            slots.append(TimeSlot(
                day=match.group(1),
                start_time=_parse_time(match.group(2)),
                end_time=_parse_time(match.group(3)),
            ))
    return slots


def _parse_enrollment(raw: str) -> tuple[int, int]:
    """'수강/정원' 형식에서 수강인원과 정원을 추출한다. 예: '17/30' → (17, 30)."""
    if not raw:
        return 0, 0
    parts = raw.split("/")
    try:
        enrolled = int(parts[0])
    except (ValueError, IndexError):
        enrolled = 0
    try:
        capacity = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        capacity = 0
    return enrolled, capacity


def _parse_detail_flags(detail: str) -> tuple[bool, bool, bool]:
    """'과목상세 정보' 컬럼에서 영어전용/IC-PBL/SMART 플래그를 추출한다.

    예: '영어전용,IC-PBL(C),SMART-F' → (True, True, True)
    """
    if not detail:
        return False, False, False
    is_english = "영어전용" in detail
    is_ic_pbl = "IC-PBL" in detail
    is_smart = "SMART" in detail
    return is_english, is_ic_pbl, is_smart


def load_from_csv(path: str) -> list[Course]:
    """한양대 수강신청 CSV(hanyang-sugang.csv)에서 Course 리스트를 로드한다.

    CSV 헤더(주요):
      학수번호, 교과목명, 학점, 수업시간, 이수구분, 설강학과,
      수강/정원, 과목상세 정보(영어전용/IC-PBL/SMART 포함)
    """
    courses: list[Course] = []
    seen: set[tuple[str, str]] = set()  # (학수번호, 설강학과) 중복 제거

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            course_id = row.get("학수번호", "").strip()
            dept = row.get("설강학과", "").strip()
            key = (course_id, dept)
            if key in seen:
                continue
            seen.add(key)

            detail = row.get("과목상세 정보", "")
            is_english, is_ic_pbl, is_smart = _parse_detail_flags(detail)

            credits_str = row.get("학점", "3").strip()
            try:
                credits = int(credits_str)
            except ValueError:
                credits = 3

            enrolled, capacity = _parse_enrollment(row.get("수강/정원", ""))

            courses.append(Course(
                course_id=course_id,
                name=row.get("교과목명", "").strip(),
                credits=credits,
                time_slots=_parse_time_slots(row.get("수업시간", "")),
                category=row.get("이수구분", "").strip(),
                department=dept,
                enrollment_count=enrolled,
                capacity=capacity,
                is_english_only=is_english,
                is_ic_pbl=is_ic_pbl,
                is_smart=is_smart,
            ))
    return courses


def load_from_json(path: str) -> list[Course]:
    """JSON 파일에서 Course 리스트를 로드한다."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    courses: list[Course] = []
    for item in data:
        courses.append(Course(
            course_id=item.get("course_id", ""),
            name=item.get("name", ""),
            credits=item.get("credits", 3),
            time_slots=_parse_time_slots(item.get("time_slots_raw", "")),
            category=item.get("category", ""),
            department=item.get("department", ""),
            enrollment_count=item.get("enrollment_count", 0),
            is_english_only=item.get("is_english_only", False),
            is_ic_pbl=item.get("is_ic_pbl", False),
            is_smart=item.get("is_smart", False),
        ))
    return courses



def load_sample_courses() -> list[Course]:
    """테스트/데모용 샘플 강의 데이터를 반환한다.

    실제 한양대 2026-1학기 강의시간표 데이터가 확보되면
    load_from_csv() 또는 load_from_json()으로 교체한다.
    """
    return [
        # 컴퓨터소프트웨어학부 전공
        Course(
            course_id="CSE3010", name="운영체제", credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 30)),
                        TimeSlot(day="수", start_time=time(9, 0), end_time=time(10, 30))],
            category="전공필수", department="컴퓨터소프트웨어학부",
            enrollment_count=45, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CSE4020", name="컴퓨터그래픽스", credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(10, 0), end_time=time(11, 30)),
                        TimeSlot(day="목", start_time=time(10, 0), end_time=time(11, 30))],
            category="전공선택", department="컴퓨터소프트웨어학부",
            enrollment_count=35, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CSE3080", name="데이터베이스", credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(13, 0), end_time=time(14, 30)),
                        TimeSlot(day="수", start_time=time(13, 0), end_time=time(14, 30))],
            category="전공필수", department="컴퓨터소프트웨어학부",
            enrollment_count=50, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CSE4050", name="소프트웨어공학", credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(13, 0), end_time=time(14, 30)),
                        TimeSlot(day="목", start_time=time(13, 0), end_time=time(14, 30))],
            category="전공선택", department="컴퓨터소프트웨어학부",
            enrollment_count=30, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CSE2010", name="자료구조", credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(10, 30), end_time=time(12, 0)),
                        TimeSlot(day="수", start_time=time(10, 30), end_time=time(12, 0))],
            category="전공필수", department="컴퓨터소프트웨어학부",
            enrollment_count=60, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CSE3050", name="인공지능", credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(15, 0), end_time=time(16, 30)),
                        TimeSlot(day="목", start_time=time(15, 0), end_time=time(16, 30))],
            category="전공선택", department="컴퓨터소프트웨어학부",
            enrollment_count=55, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CSE4060", name="캡스톤디자인", credits=3,
            time_slots=[TimeSlot(day="금", start_time=time(9, 0), end_time=time(12, 0))],
            category="전공필수", department="컴퓨터소프트웨어학부",
            enrollment_count=25, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        # 교양
        Course(
            course_id="GEN0001", name="기초학술영어", credits=2,
            time_slots=[TimeSlot(day="월", start_time=time(15, 0), end_time=time(16, 30)),
                        TimeSlot(day="수", start_time=time(15, 0), end_time=time(16, 30))],
            category="교양필수", department="교양교육원",
            enrollment_count=30, is_english_only=True, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="GEN0002", name="전문학술영어", credits=2,
            time_slots=[TimeSlot(day="화", start_time=time(9, 0), end_time=time(10, 30)),
                        TimeSlot(day="목", start_time=time(9, 0), end_time=time(10, 30))],
            category="교양필수", department="교양교육원",
            enrollment_count=28, is_english_only=True, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="CUL3011", name="커리어개발Ⅰ", credits=1,
            time_slots=[TimeSlot(day="금", start_time=time(13, 0), end_time=time(14, 0))],
            category="교양선택", department="교양교육원",
            enrollment_count=40, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        # 전기공학부
        Course(
            course_id="ELE3010", name="회로이론", credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 30)),
                        TimeSlot(day="수", start_time=time(9, 0), end_time=time(10, 30))],
            category="전공필수", department="전기공학부",
            enrollment_count=40, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="ELE4020", name="전력전자", credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(10, 0), end_time=time(11, 30)),
                        TimeSlot(day="목", start_time=time(10, 0), end_time=time(11, 30))],
            category="전공선택", department="전기공학부",
            enrollment_count=25, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        # 경영학부
        Course(
            course_id="BUS2010", name="마케팅원론", credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(13, 0), end_time=time(14, 30)),
                        TimeSlot(day="목", start_time=time(13, 0), end_time=time(14, 30))],
            category="전공필수", department="경영학부",
            enrollment_count=70, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        Course(
            course_id="BUS3020", name="재무관리", credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(13, 0), end_time=time(14, 30)),
                        TimeSlot(day="수", start_time=time(13, 0), end_time=time(14, 30))],
            category="전공선택", department="경영학부",
            enrollment_count=55, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
        # 핵심교양
        Course(
            course_id="HAI1001", name="인공지능의이해", credits=3,
            time_slots=[TimeSlot(day="수", start_time=time(16, 0), end_time=time(17, 30)),
                        TimeSlot(day="금", start_time=time(16, 0), end_time=time(17, 30))],
            category="핵심교양", department="교양교육원",
            enrollment_count=80, is_english_only=False, is_ic_pbl=False, is_smart=False,
        ),
    ]


def search_courses(
    all_courses: list[Course],
    query: str | None = None,
    department: str | None = None,
    category: str | None = None,
) -> list[Course]:
    """과목명/학과/이수구분으로 강의를 검색한다."""
    results = all_courses
    if department:
        results = [c for c in results if department in c.department]
    if category:
        results = [c for c in results if category in c.category]
    if query:
        q = query.strip()
        results = [c for c in results if q in c.name or q in c.course_id]
    return results
