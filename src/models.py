"""핵심 데이터 모델 정의.

한양대 서울캠퍼스 시간표 추천 챗봇에서 사용하는 모든 dataclass를 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time


@dataclass
class StudentInfo:
    """학생 정보."""

    student_id: str
    grade: int
    semester: int
    is_graduating: bool
    is_extended: bool
    is_2026_freshman: bool
    department: str
    has_multiple_major: bool


@dataclass
class TimeSlot:
    """강의 시간대."""

    day: str
    start_time: time
    end_time: time


@dataclass
class Course:
    """교과목 정보."""

    course_id: str
    name: str
    credits: int
    time_slots: list[TimeSlot]
    category: str
    department: str
    enrollment_count: int
    is_english_only: bool
    is_ic_pbl: bool
    is_smart: bool


@dataclass
class Page:
    """파싱된 페이지."""

    page_number: int
    content: str
    metadata: dict


@dataclass
class ParsedData:
    """전처리된 구조화 데이터."""

    schedule: dict
    credit_rules: dict
    cancel_rules: dict
    prerequisites: dict
    equivalent_courses: dict
    curriculum_rules: dict


@dataclass
class PrerequisiteRule:
    """선수-후수 교과목 규칙."""

    prerequisite: str
    subsequent: str
    exemption_grades: list[str]


@dataclass
class EquivalentCourse:
    """동일/대치 교과목."""

    old_course_id: str
    old_name: str
    new_course_id: str
    new_name: str
    relation_type: str


@dataclass
class PreprocessorWarning:
    """전처리 경고."""

    page_number: int
    line_number: int
    message: str


@dataclass
class CreditValidationResult:
    """학점 검증 결과."""

    is_valid: bool
    min_credits: int
    max_credits: int
    current_credits: int
    extra_credits: int
    warnings: list[str]


@dataclass
class ConflictResult:
    """시간표 충돌 검증 결과."""

    has_conflict: bool
    conflicts: list[tuple[Course, Course, TimeSlot]]


@dataclass
class PrerequisiteWarning:
    """선수과목 미이수 경고."""

    course_name: str
    missing_prerequisite: str
    message: str


@dataclass
class CancellationResult:
    """폐강 판정 결과."""

    is_at_risk: bool
    reason: str
    applied_rule: str


@dataclass
class EquivalentAdvice:
    """동일/대치 교과목 안내."""

    course_name: str
    related_course: str
    relation_type: str
    message: str


@dataclass
class DepartmentInfo:
    """학과 정보."""

    name: str
    enrollment_by_grade: dict[int, int]


@dataclass
class ChunkSource:
    """RAG 청크 출처."""

    page_number: int
    chunk_text: str
    similarity_score: float


@dataclass
class RAGResponse:
    """RAG 응답."""

    answer: str
    sources: list[ChunkSource]
    has_evidence: bool


@dataclass
class ScheduleResult:
    """시간표 추천 결과."""

    timetable: list[list[str]]
    warnings: list[str]
    credit_info: CreditValidationResult
    conflicts: ConflictResult
