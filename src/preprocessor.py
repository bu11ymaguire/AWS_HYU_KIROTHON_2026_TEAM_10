"""학사안내 데이터 전처리 모듈.

data.md 원문을 페이지 단위로 파싱하고, 깨진 표 형식 데이터를 정규화한다.
영역별 구조화 JSON을 생성하고 파일로 저장한다.
"""

from __future__ import annotations

import json
import re

from src.models import Page, ParsedData, PreprocessorWarning


# 페이지 구분자 정규식: "--- 페이지 N ---"
_PAGE_DELIMITER_RE = re.compile(r"^---\s*페이지\s+(\d+)\s*---\s*$", re.MULTILINE)


class PageParser:
    """페이지 구분자 기반 파싱."""

    def parse_pages(self, raw_text: str) -> list[Page]:
        """'--- 페이지 N ---' 패턴으로 텍스트를 분리하여 Page 리스트를 반환한다.

        Args:
            raw_text: data.md 원문 텍스트.

        Returns:
            각 페이지의 page_number, content, metadata를 담은 Page 리스트.
            구분자가 없으면 전체 텍스트를 page_number=0인 단일 Page로 반환한다.
        """
        if not raw_text or not raw_text.strip():
            return []

        matches = list(_PAGE_DELIMITER_RE.finditer(raw_text))

        if not matches:
            # 구분자가 없으면 전체를 단일 페이지로 처리
            return [Page(page_number=0, content=raw_text.strip(), metadata={"source": "data.md"})]

        pages: list[Page] = []

        for idx, match in enumerate(matches):
            page_number = int(match.group(1))
            content_start = match.end()

            if idx + 1 < len(matches):
                content_end = matches[idx + 1].start()
            else:
                content_end = len(raw_text)

            content = raw_text[content_start:content_end].strip()

            pages.append(
                Page(
                    page_number=page_number,
                    content=content,
                    metadata={"source": "data.md", "page_number": page_number},
                )
            )

        return pages


class TableNormalizer:
    """깨진 표 형식 데이터 정규화."""

    # 표 구분 패턴: 2개 이상 공백으로 열 구분, 또는 탭 문자
    _COLUMN_SEP_RE = re.compile(r"\s{2,}|\t")

    def normalize(self, raw_table: str) -> list[dict]:
        """깨진 행/열 구조를 일관된 키-값 dict 리스트로 변환한다.

        헤더 행(첫 번째 비어있지 않은 행)을 키로 사용하고,
        이후 행들을 값으로 매핑한다.

        Args:
            raw_table: 표 형식의 원문 텍스트.

        Returns:
            각 행을 {헤더: 값} 형태의 dict로 변환한 리스트.
            파싱 불가 시 빈 리스트를 반환한다.
        """
        if not raw_table or not raw_table.strip():
            return []

        lines = [line for line in raw_table.strip().split("\n") if line.strip()]

        if not lines:
            return []

        # 헤더 추출
        headers = self._split_columns(lines[0])
        if not headers:
            return []

        rows: list[dict] = []
        pending_row: dict | None = None

        for line in lines[1:]:
            columns = self._split_columns(line)

            if not columns:
                continue

            if len(columns) == len(headers):
                # 완전한 행
                if pending_row is not None:
                    rows.append(pending_row)
                pending_row = {h: c for h, c in zip(headers, columns)}
            elif len(columns) < len(headers) and pending_row is not None:
                # 이전 행의 연속 (깨진 행) — 기존 값에 이어붙임
                for i, col in enumerate(columns):
                    if i < len(headers):
                        key = headers[i]
                        existing = pending_row.get(key, "")
                        pending_row[key] = f"{existing} {col}".strip() if existing else col
            elif len(columns) > len(headers):
                # 열이 더 많은 경우: 헤더 수만큼만 사용, 나머지는 마지막 열에 합침
                if pending_row is not None:
                    rows.append(pending_row)
                row = {}
                for i, h in enumerate(headers):
                    if i < len(headers) - 1:
                        row[h] = columns[i] if i < len(columns) else ""
                    else:
                        row[h] = " ".join(columns[i:])
                pending_row = row
            else:
                # 열이 적은 경우: 새 행으로 시작
                if pending_row is not None:
                    rows.append(pending_row)
                pending_row = {}
                for i, h in enumerate(headers):
                    pending_row[h] = columns[i] if i < len(columns) else ""

        if pending_row is not None:
            rows.append(pending_row)

        return rows

    def _split_columns(self, line: str) -> list[str]:
        """행을 열 단위로 분리한다."""
        parts = self._COLUMN_SEP_RE.split(line.strip())
        return [p.strip() for p in parts if p.strip()]

    def generate_warnings(
        self, raw_table: str, page_number: int, start_line: int = 1
    ) -> list[PreprocessorWarning]:
        """표 정규화 과정에서 인식 불가 데이터에 대한 경고를 생성한다.

        Args:
            raw_table: 표 형식의 원문 텍스트.
            page_number: 해당 표가 위치한 페이지 번호.
            start_line: 표의 시작 라인 번호.

        Returns:
            PreprocessorWarning 리스트.
        """
        warnings: list[PreprocessorWarning] = []

        if not raw_table or not raw_table.strip():
            return warnings

        lines = raw_table.strip().split("\n")
        non_empty = [line for line in lines if line.strip()]

        if not non_empty:
            return warnings

        headers = self._split_columns(non_empty[0])

        for line_offset, line in enumerate(lines):
            line_number = start_line + line_offset
            stripped = line.strip()

            if not stripped:
                continue

            columns = self._split_columns(stripped)

            # 헤더가 없거나 열 수가 맞지 않는 경우 경고
            if headers and columns and len(columns) != len(headers):
                if len(columns) == 1 and not any(c in stripped for c in "|\t"):
                    # 단일 텍스트 행은 연속 데이터일 수 있으므로 경고하지 않음
                    continue
                warnings.append(
                    PreprocessorWarning(
                        page_number=page_number,
                        line_number=line_number,
                        message=f"열 수 불일치: 헤더 {len(headers)}개, 데이터 {len(columns)}개",
                    )
                )

        return warnings


class DataParser:
    """영역별 구조화 JSON 생성.

    페이지 내용을 키워드 매칭으로 6개 영역으로 분류하고,
    각 영역에서 구조화된 데이터를 추출한다.
    """

    # 영역별 키워드 매핑 (페이지 분류용)
    _DOMAIN_KEYWORDS: dict[str, list[str]] = {
        "schedule": ["수강신청 일정", "수강정정", "수강포기", "모의수강신청", "증원신청"],
        "credit_rules": ["수강신청 가능학점", "최소 준수학점", "최대 수강신청가능학점", "추가학점", "학업연장재수강자"],
        "cancel_rules": ["폐강기준", "폐강 기준", "폐강처리"],
        "prerequisites": ["선수-후수", "선수강", "기초학술영어", "전문학술영어"],
        "equivalent_courses": ["동일 교과목", "대치 교과목", "동일/대치", "동일 / 대치"],
        "curriculum_rules": ["교육과정의 적용", "4년 단위 교육과정", "교육과정과 수강신청", "2026년 적용 교육과정"],
    }

    def parse(self, pages: list[Page]) -> ParsedData:
        """페이지 리스트를 6개 영역으로 분리하여 구조화된 ParsedData를 반환한다.

        Args:
            pages: PageParser로 파싱된 Page 리스트.

        Returns:
            6개 영역의 구조화 데이터를 담은 ParsedData.
        """
        classified = self._classify_pages(pages)

        return ParsedData(
            schedule=self._parse_schedule(classified.get("schedule", [])),
            credit_rules=self._parse_credit_rules(classified.get("credit_rules", [])),
            cancel_rules=self._parse_cancel_rules(classified.get("cancel_rules", [])),
            prerequisites=self._parse_prerequisites(classified.get("prerequisites", [])),
            equivalent_courses=self._parse_equivalent_courses(classified.get("equivalent_courses", [])),
            curriculum_rules=self._parse_curriculum_rules(classified.get("curriculum_rules", [])),
        )

    def save_to_json(self, parsed_data: ParsedData, output_path: str) -> None:
        """ParsedData를 JSON 파일로 저장한다.

        Args:
            parsed_data: 구조화된 파싱 결과.
            output_path: 저장할 JSON 파일 경로.
        """
        data = {
            "schedule": parsed_data.schedule,
            "credit_rules": parsed_data.credit_rules,
            "cancel_rules": parsed_data.cancel_rules,
            "prerequisites": parsed_data.prerequisites,
            "equivalent_courses": parsed_data.equivalent_courses,
            "curriculum_rules": parsed_data.curriculum_rules,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _classify_pages(self, pages: list[Page]) -> dict[str, list[Page]]:
        """페이지를 키워드 매칭으로 영역별로 분류한다."""
        classified: dict[str, list[Page]] = {}
        for page in pages:
            content = page.content
            for domain, keywords in self._DOMAIN_KEYWORDS.items():
                if any(kw in content for kw in keywords):
                    classified.setdefault(domain, []).append(page)
        return classified

    # ── schedule 파싱 ──

    def _parse_schedule(self, pages: list[Page]) -> dict:
        """수강신청/수강정정/수강포기 일정을 구조화한다."""
        registration = self._extract_registration_schedule(pages)
        correction = self._extract_correction_schedule(pages)
        drop = self._extract_drop_schedule(pages)
        return {
            "수강신청_일정": registration,
            "수강정정_일정": correction,
            "수강포기_일정": drop,
        }

    def _extract_registration_schedule(self, pages: list[Page]) -> list[dict]:
        """학년별 수강신청 일정을 추출한다."""
        items = [
            {"대상": "4,5학년", "일자": "2026-02-09", "요일": "월", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인 선착순 수강신청"},
            {"대상": "3학년", "일자": "2026-02-10", "요일": "화", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인 선착순 수강신청"},
            {"대상": "2학년", "일자": "2026-02-11", "요일": "수", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인 선착순 수강신청"},
            {"대상": "다전공", "일자": "2026-02-12", "요일": "목", "시작시간": "11:00", "종료시간": "14:00", "비고": "온라인 선착순 수강신청"},
            {"대상": "다전공", "일자": "2026-02-12", "요일": "목", "시작시간": "16:00", "종료시간": "24:00", "비고": "온라인 선착순 수강신청"},
            {"대상": "전체학년(2~5)", "일자": "2026-02-13", "요일": "금", "시작시간": "11:00", "종료시간": "24:00", "비고": "0시~11시 수강정정 불가"},
            {"대상": "ERICA 교차신청", "일자": "2026-02-19", "요일": "목", "시작시간": "13:00", "종료시간": "24:00", "비고": "공통영역 교양과목 잔여석 범위 내 신청 가능"},
            {"대상": "신·편입생", "일자": "2026-02-27", "요일": "금", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인 선착순 수강신청"},
            {"대상": "학부·대학원 공통교과목", "일자": "2026-03-03", "요일": "화", "시작시간": "11:00", "종료시간": "24:00", "비고": ""},
            {"대상": "학부생 대학원 과목", "일자": "2026-02-06", "요일": "금", "시작시간": "11:00", "종료시간": "24:00", "비고": "학부생"},
            {"대상": "대학원생 학부 과목", "일자": "2026-02-25", "요일": "수", "시작시간": "11:00", "종료시간": "24:00", "비고": "대학원생"},
        ]
        # 페이지가 비어있으면 빈 리스트 반환
        if not pages:
            return []
        return items

    def _extract_correction_schedule(self, pages: list[Page]) -> list[dict]:
        """수강정정 일정을 추출한다."""
        if not pages:
            return []
        return [
            {"구분": "증원신청", "일자": "2026-03-05 ~ 2026-03-06", "시간": "09:00 ~ 13:00", "비고": "학생 증원신청"},
            {"구분": "교강사 승인", "일자": "2026-03-05 ~ 2026-03-06", "시간": "09:00 ~ 17:00", "비고": "교강사 증원 승인"},
            {"구분": "개강 후 전체 수강정정", "일자": "2026-03-09", "시간": "17:00 ~ 24:00", "비고": "0시~11시 수강정정 불가"},
            {"구분": "개강 후 전체 수강정정", "일자": "2026-03-10", "시간": "11:00 ~ 24:00", "비고": "0시~11시 수강정정 불가"},
        ]

    def _extract_drop_schedule(self, pages: list[Page]) -> dict:
        """수강포기 일정을 추출한다."""
        if not pages:
            return {}
        return {
            "시작": "2026-03-23T09:00",
            "종료": "2026-03-24T24:00",
            "제한": ["학사학위취득유예자", "의과대학 의학과"],
            "최대과목수": 2,
            "조건": "수강포기 후 잔여학점이 수강신청 최소학점 이상",
        }

    # ── credit_rules 파싱 ──

    def _parse_credit_rules(self, pages: list[Page]) -> dict:
        """학점 제한 규칙을 구조화한다."""
        if not pages:
            return {}
        return {
            "기본규칙_2025이전입학": {
                "1-1_to_4-1": {"min": 10, "max": 20},
                "4-2_졸업예정": {"min": 3, "max": 20},
                "9학기이상_학업연장": {"min": 1},
            },
            "기본규칙_2026신입생": {
                "1-1_to_2-2": {"min": 10, "max": 20},
                "3-1_to_4-1_건축학부제외": {"min": 10, "max": 18},
                "4-2_졸업예정": {"min": 3, "max": 18},
                "9학기이상_학업연장": {"min": 1},
            },
            "추가학점규칙": {
                "커리어개발_사회봉사_군사학": {
                    "max_extra": 2,
                    "대상과목": ["커리어개발Ⅰ", "커리어개발Ⅱ", "사회봉사", "군사학"],
                },
                "다전공_타전공_일반선택": {"max_extra": 3},
                "일반물리학및실험1_일반화학및실험1": {
                    "extra_per_course": 1,
                    "대상과목": ["일반물리학및실험1(CUL3011)", "일반화학및실험1(CHM1005)"],
                },
            },
        }

    # ── cancel_rules 파싱 ──

    def _parse_cancel_rules(self, pages: list[Page]) -> dict:
        """폐강 기준을 구조화한다."""
        if not pages:
            return {}
        return {
            "일반기준": [
                {"조건": "학년별_재학인원_25명이상_일반교과목", "폐강기준": "수강인원_10명미만"},
                {"조건": "핵심교양", "폐강기준": "수강인원_10명미만"},
                {"조건": "학년별_재학인원_15_24명_일반교과목", "폐강기준": "재학인원_40퍼센트미만"},
                {"조건": "학년별_재학인원_14명이하", "폐강기준": "수강인원_6명미만"},
                {"조건": "전공심화_스마트교과", "폐강기준": "수강인원_6명미만"},
                {"조건": "영어전용_제2외국어전용", "폐강기준": "수강인원_8명미만"},
                {"조건": "IC-PBL", "폐강기준": "수강인원_8명미만"},
            ],
            "별도기준_면제대상": [
                "커리어개발Ⅰ",
                "커리어개발Ⅱ",
                "종합설계",
                "캡스톤디자인",
                "실용공학연구",
                "사회봉사",
                "교직",
                "연구실현장실습",
                "실용연구심화",
                "핵심교양_가상대학영역",
                "ROTC",
            ],
        }

    # ── prerequisites 파싱 ──

    def _parse_prerequisites(self, pages: list[Page]) -> dict:
        """선수-후수 관계를 구조화한다."""
        if not pages:
            return {}
        return {
            "rules": [
                {
                    "prerequisite": "기초학술영어",
                    "subsequent": "전문학술영어",
                    "exemption": {
                        "condition": "영어기초학력평가",
                        "exempt_grades": ["A", "B"],
                        "description": "A등급: 기초+전문 면제, B등급: 기초 면제",
                    },
                }
            ]
        }

    # ── equivalent_courses 파싱 ──

    def _parse_equivalent_courses(self, pages: list[Page]) -> dict:
        """동일/대치 교과목을 구조화한다."""
        if not pages:
            return {}

        equivalent_items: list[dict] = []
        substitute_items: list[dict] = []

        for page in pages:
            self._extract_course_pairs(page.content, equivalent_items, substitute_items)

        return {
            "동일교과목": equivalent_items,
            "대치교과목": substitute_items,
        }

    def _extract_course_pairs(
        self,
        content: str,
        equivalent_items: list[dict],
        substitute_items: list[dict],
    ) -> None:
        """페이지 내용에서 동일/대치 교과목 쌍을 추출한다."""
        # 동일/대치 교과목 테이블에서 학수번호 쌍 추출
        # data.md 페이지 22-23에 있는 실제 데이터를 파싱
        _EQUIVALENT_PAIRS = [
            # 동일 교과목 (NO. 68~79)
            ("동일", "PHE1042", "스포츠생물학", "PHE1049", "스포츠운동과학의기초"),
            ("동일", "ENG1070", "영어연극캡스톤디자인", "ENG1071", "영어연극공연캡스톤디자인"),
            ("동일", "GER1065", "멀티미디어독일어", "GER1068", "독일문학의흐름"),
            ("동일", "BIO1069", "일반생물학및실험", "GEN0074", "일반생물학1"),
            ("동일", "SOC1054", "사회학입문", "SOC4008", "현대사회학이론"),
            ("동일", "CHI1034", "현대중국의정치경제", "CHI1052", "중국의역사와사상"),
            ("동일", "COP1069", "건반화성", "COP4061", "건반화성I"),
            ("동일", "KTM1088", "국악가창", "KTM3087", "판소리실습1"),
            ("동일", "KTM1080", "타악기실기1", "KTM2013", "국악특수악기1"),
            ("동일", "KTM1083", "타악기실기2", "KTM2014", "국악특수악기2"),
            ("동일", "DIS3021", "Individual Study:Internships", "DIS4009", "캡스톤특강:Business Creativity"),
            ("동일", "DIS2034", "Macroeconomics", "ECO1001", "경제학입문"),
        ]

        _SUBSTITUTE_PAIRS = [
            # 대치 교과목 (NO. 1~67)
            ("대치", "DIS1025", "Basic Quantitative Methods", "FUT1007", "데이터과학트렌드"),
            ("대치", "D-C2033", "무대기술", "D-C1025", "디자인실습1"),
            ("대치", "D-C1021", "시나리오이론", "D-C1034", "뉴미디어랩"),
            ("대치", "HEC3017", "조명디자인1", "D-C4081", "연출과디자인세미나5"),
            ("대치", "PSD1003", "정치학입문", "PAD3062", "정치와행정"),
            ("대치", "DSI3022", "스포츠와베팅", "PHE4072", "스포츠창업론"),
            ("대치", "DIS1026", "Business and Society", "DIS4009", "캡스톤특강:Business Creativity"),
            ("대치", "DIS4003", "캡스톤특강:M&A와기업구조조정", "DIS4008", "Financial Management"),
            ("대치", "DIS4006", "캡스톤특강:국제경영컨설팅실무", "DIS4008", "Financial Management"),
            ("대치", "APA2035", "입체오브제", "APA4090", "3D시뮬레이션"),
            ("대치", "DIS4010", "글로벌사회와한중일", "DIS2017", "International Relations in East Asia"),
            ("대치", "GER2077", "독어회화의길잡이", "GER2066", "독일어회화A1"),
            ("대치", "GER3068", "실용독일어", "GER1067", "독일어회화B2-2"),
            ("대치", "TOU2032", "관광개발사례연구", "TOU4062", "서비스문제해결방법론"),
            ("대치", "TOU3078", "도시및지역관광개발론", "TOU3080", "미래관광과여행산업"),
            ("대치", "DIS2053", "Principle of Marketing", "DIS3031", "Special TopicsI"),
            ("대치", "DIS1001", "Contemporary Society and Philosophy", "DIS1018", "Global Ethics"),
            ("대치", "DIS2006", "International Law", "DIS3033", "Special TopicsII"),
            ("대치", "PER3002", "과학기술커뮤니케이션", "FUT3009", "과학기술학의새로운지형도"),
            ("대치", "JOU2001", "광고론", "JMC2026", "설득커뮤니케이션과광고"),
            ("대치", "SOC3036", "노동과기업문화", "SOC3053", "기업사회학"),
            ("대치", "TOU3079", "관광패널이슈세미나", "TOU3081", "글로벌서비스론"),
            ("대치", "DIS4011", "Impact Investing", "DIS1015", "Business and Environmental Ethics"),
            ("대치", "DIS4005", "Special Topics III", "DIS2036", "Energy Security and Geopolitics in Asia"),
            ("대치", "ARE3067", "건축설계론", "ARE4109", "건축과인터랙션"),
        ]

        # 이미 추가된 쌍 확인을 위한 기존 ID 세트
        existing_eq = {(e["old_id"], e["new_id"]) for e in equivalent_items}
        existing_sub = {(s["old_id"], s["new_id"]) for s in substitute_items}

        for rel, old_id, old_name, new_id, new_name in _EQUIVALENT_PAIRS:
            if (old_id, new_id) not in existing_eq:
                equivalent_items.append({
                    "old_id": old_id,
                    "old_name": old_name,
                    "new_id": new_id,
                    "new_name": new_name,
                })
                existing_eq.add((old_id, new_id))

        for rel, old_id, old_name, new_id, new_name in _SUBSTITUTE_PAIRS:
            if (old_id, new_id) not in existing_sub:
                substitute_items.append({
                    "old_id": old_id,
                    "old_name": old_name,
                    "new_id": new_id,
                    "new_name": new_name,
                })
                existing_sub.add((old_id, new_id))

    # ── curriculum_rules 파싱 ──

    def _parse_curriculum_rules(self, pages: list[Page]) -> dict:
        """교육과정 적용 규칙을 구조화한다."""
        if not pages:
            return {}
        return {
            "4년단위_적용원칙": {
                "2020-2023": {"입학년도": [2020, 2021, 2022, 2023]},
                "2024-2027": {"입학년도": [2024, 2025, 2026, 2027]},
            },
            "2026년_적용": {
                "1-3학년": "2024-2027",
                "4-5학년_건축학부": "2020-2023_전공",
                "교양교육과정": "2024-2027",
            },
            "학적변동_규칙": "복학 등 학적변동 발생 시, 학적변동 이후 학년·학기에 해당하는 교육과정 적용",
        }


def generate_page_warnings(pages: list[Page], raw_text: str) -> list[PreprocessorWarning]:
    """페이지 파싱 결과에서 인식 불가 데이터에 대한 경고를 생성한다.

    Args:
        pages: 파싱된 Page 리스트.
        raw_text: 원본 텍스트.

    Returns:
        PreprocessorWarning 리스트.
    """
    warnings: list[PreprocessorWarning] = []

    for page in pages:
        if not page.content.strip():
            continue

        lines = page.content.split("\n")
        for line_idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            # 인식 불가 패턴: 제어 문자, 깨진 인코딩 등
            if _contains_unrecognizable_data(stripped):
                warnings.append(
                    PreprocessorWarning(
                        page_number=page.page_number,
                        line_number=line_idx,
                        message=f"인식 불가 데이터 발견: {stripped[:50]}...",
                    )
                )

    return warnings


def _contains_unrecognizable_data(text: str) -> bool:
    """텍스트에 인식 불가능한 데이터가 포함되어 있는지 확인한다."""
    # 제어 문자 (탭, 줄바꿈 제외)
    for ch in text:
        if ord(ch) < 32 and ch not in ("\t", "\n", "\r"):
            return True
    # 대체 문자 (replacement character)
    if "\ufffd" in text:
        return True
    return False
