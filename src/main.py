"""한양대 서울캠퍼스 수강신청 도우미 엔트리포인트.

data.md 전처리 → 구조화 JSON 생성 → 벡터 DB 인덱싱 →
각 검증기 초기화 → ChatBot 인스턴스 생성 → CLI 실행.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from src.cancellation_checker import CancellationChecker
from src.chatbot import ChatBot
from src.conflict_checker import ConflictChecker
from src.credit_validator import CreditValidator
from src.equivalent_manager import EquivalentManager
from src.models import EquivalentCourse, ParsedData, PrerequisiteRule
from src.preprocessor import DataParser, PageParser
from src.prerequisite_checker import PrerequisiteChecker
from src.rag_pipeline import RAGPipeline
from src.schedule_recommender import ScheduleRecommender

_DATA_FILE = "data.md"
_VECTOR_DB_PATH = "data/chroma_db"


def _load_prerequisite_rules(prerequisites: dict) -> list[PrerequisiteRule]:
    """ParsedData.prerequisites dict를 PrerequisiteRule 리스트로 변환한다."""
    rules: list[PrerequisiteRule] = []
    for entry in prerequisites.get("rules", []):
        exemption = entry.get("exemption", {})
        rules.append(
            PrerequisiteRule(
                prerequisite=entry["prerequisite"],
                subsequent=entry["subsequent"],
                exemption_grades=exemption.get("exempt_grades", []),
            )
        )
    return rules


def _load_equivalent_courses(equivalent_courses: dict) -> list[EquivalentCourse]:
    """ParsedData.equivalent_courses dict를 EquivalentCourse 리스트로 변환한다."""
    items: list[EquivalentCourse] = []
    for entry in equivalent_courses.get("동일교과목", []):
        items.append(
            EquivalentCourse(
                old_course_id=entry["old_id"],
                old_name=entry["old_name"],
                new_course_id=entry["new_id"],
                new_name=entry["new_name"],
                relation_type="동일",
            )
        )
    for entry in equivalent_courses.get("대치교과목", []):
        items.append(
            EquivalentCourse(
                old_course_id=entry["old_id"],
                old_name=entry["old_name"],
                new_course_id=entry["new_id"],
                new_name=entry["new_name"],
                relation_type="대치",
            )
        )
    return items


def main() -> None:
    """메인 실행 함수."""
    load_dotenv()

    # 1. API 키 확인
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print(
            "오류: OPENAI_API_KEY가 설정되지 않았습니다.\n"
            ".env 파일에 OPENAI_API_KEY를 설정해주세요."
        )
        sys.exit(1)

    # 2. data.md 읽기
    if not os.path.exists(_DATA_FILE):
        print(f"오류: '{_DATA_FILE}' 파일을 찾을 수 없습니다.")
        sys.exit(1)

    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()

    # 3. 페이지 파싱
    page_parser = PageParser()
    pages = page_parser.parse_pages(raw_text)

    # 4. 구조화 JSON 생성
    data_parser = DataParser()
    parsed_data: ParsedData = data_parser.parse(pages)

    # 5. RAG 파이프라인 — 벡터 DB 인덱싱
    rag_pipeline = RAGPipeline(vector_db_path=_VECTOR_DB_PATH)
    rag_pipeline.index(pages)

    # 6. 검증기/판정기 초기화
    credit_validator = CreditValidator(parsed_data.credit_rules)
    conflict_checker = ConflictChecker()
    prerequisite_checker = PrerequisiteChecker(
        _load_prerequisite_rules(parsed_data.prerequisites)
    )
    cancellation_checker = CancellationChecker(parsed_data.cancel_rules)
    equivalent_manager = EquivalentManager(
        _load_equivalent_courses(parsed_data.equivalent_courses)
    )

    # 7. 시간표 추천기 생성
    schedule_recommender = ScheduleRecommender(
        credit_validator=credit_validator,
        conflict_checker=conflict_checker,
        prerequisite_checker=prerequisite_checker,
        cancellation_checker=cancellation_checker,
        equivalent_manager=equivalent_manager,
    )

    # 8. 강의 데이터 로드
    from src.course_loader import load_sample_courses, load_from_csv

    courses_csv = os.environ.get("COURSES_CSV_PATH", "lec/hanyang-sugang.csv")
    if os.path.exists(courses_csv):
        available_courses = load_from_csv(courses_csv)
    else:
        available_courses = load_sample_courses()

    # 9. 챗봇 생성 및 실행
    chatbot = ChatBot(
        rag_pipeline=rag_pipeline,
        schedule_recommender=schedule_recommender,
        credit_validator=credit_validator,
        parsed_data=parsed_data,
        available_courses=available_courses,
    )
    chatbot.run()


if __name__ == "__main__":
    main()
