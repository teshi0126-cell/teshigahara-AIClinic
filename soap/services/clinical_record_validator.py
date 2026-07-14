import re

from .soap_service import SOAPService


class ClinicalRecordValidator:
    """
    生成AIを使わず、原文とSOAPの機械的な整合性を確認する。

    判定はSOAPを自動変更せず、医師確認用のチェックとして返す。
    """

    META_PHRASES = (
        "医師発言あり",
        "患者が回答",
        "と回答",
        "医師は述べ",
        "医師が述べ",
    )

    def validate(
        self,
        source_note: str,
        encounter: dict,
        soap_text: str,
    ) -> list[dict]:
        source = source_note or ""
        soap = soap_text or ""
        encounter_data = (
            encounter
            if isinstance(encounter, dict)
            else {}
        )

        unexpected_numbers = self.find_unexpected_numbers(
            source,
            soap,
        )
        has_unknown = (
            "聞き取り不明" in soap
            or "［聞き取り不明］" in soap
        )
        oa_duplicates = self.find_oa_duplicates(soap)
        meta_phrases = [
            phrase
            for phrase in self.META_PHRASES
            if phrase in soap
        ]
        unsupported_subjective = (
            self.has_subjective_content(soap)
            and not self.has_subjective_evidence(
                encounter_data
            )
        )

        return [
            self.build_check(
                item=(
                    "原文にない数値の追加なし"
                    if not unexpected_numbers
                    else (
                        "原文にない数値を確認："
                        + "、".join(unexpected_numbers)
                    )
                ),
                passed=not unexpected_numbers,
            ),
            self.build_check(
                item=(
                    "聞き取り不明語のSOAP混入なし"
                    if not has_unknown
                    else "SOAP内の聞き取り不明語を確認"
                ),
                passed=not has_unknown,
            ),
            self.build_check(
                item=(
                    "OとAの単純重複なし"
                    if not oa_duplicates
                    else (
                        "OとAの重複を確認："
                        + "、".join(oa_duplicates)
                    )
                ),
                passed=not oa_duplicates,
            ),
            self.build_check(
                item=(
                    "報告調のメタ表現なし"
                    if not meta_phrases
                    else (
                        "メタ表現を確認："
                        + "、".join(meta_phrases)
                    )
                ),
                passed=not meta_phrases,
            ),
            self.build_check(
                item=(
                    "Sの患者回答・問診根拠あり"
                    if not unsupported_subjective
                    else "Sの患者回答・問診根拠を確認"
                ),
                passed=not unsupported_subjective,
            ),
        ]

    @staticmethod
    def build_check(
        item: str,
        passed: bool,
    ) -> dict:
        return {
            "category": "記録品質",
            "item": item,
            "level": "low" if passed else "high",
            "checked": passed,
        }

    @staticmethod
    def extract_numbers(text: str) -> set[str]:
        return set(
            re.findall(
                r"(?<![A-Za-z])\d+(?:\.\d+)?",
                text or "",
            )
        )

    def find_unexpected_numbers(
        self,
        source_note: str,
        soap_text: str,
    ) -> list[str]:
        source_numbers = self.extract_numbers(
            source_note
        )
        soap_numbers = self.extract_numbers(
            soap_text
        )

        return sorted(
            soap_numbers - source_numbers
        )

    @staticmethod
    def section_bullets(
        soap_text: str,
        section: str,
    ) -> list[str]:
        items = []
        current_section = ""

        for line in (soap_text or "").splitlines():
            stripped = line.strip()
            header = re.match(
                r"^([SOAP])[：:]$",
                stripped,
                re.IGNORECASE,
            )

            if header:
                current_section = (
                    header.group(1).upper()
                )
                continue

            if (
                current_section == section.upper()
                and stripped.startswith(("-", "・"))
            ):
                item = stripped.lstrip("-・").strip()

                if item:
                    items.append(item)

        return items

    def find_oa_duplicates(
        self,
        soap_text: str,
    ) -> list[str]:
        objective_items = {
            SOAPService.normalize_for_oa_comparison(
                item
            )
            for item in self.section_bullets(
                soap_text,
                "O",
            )
        }
        objective_items.discard("")

        duplicates = []

        for item in self.section_bullets(
            soap_text,
            "A",
        ):
            normalized = (
                SOAPService.normalize_for_oa_comparison(
                    item
                )
            )

            if (
                normalized
                and normalized in objective_items
            ):
                duplicates.append(item)

        return duplicates

    def has_subjective_content(
        self,
        soap_text: str,
    ) -> bool:
        return bool(
            self.section_bullets(
                soap_text,
                "S",
            )
        )

    @staticmethod
    def has_subjective_evidence(
        encounter: dict,
    ) -> bool:
        intake = encounter.get("intake", {})
        encounter_section = encounter.get(
            "encounter",
            {},
        )

        if not isinstance(intake, dict):
            intake = {}

        if not isinstance(encounter_section, dict):
            encounter_section = {}

        evidence_fields = [
            encounter.get("chief_complaint"),
            encounter.get("history"),
            encounter.get("subjective_symptoms"),
            intake.get("raw_text"),
            intake.get("chief_complaint"),
            intake.get("history"),
            intake.get("subjective_symptoms"),
            encounter_section.get("patient_answers"),
        ]

        for value in evidence_fields:
            if isinstance(value, str) and value.strip():
                return True

            if isinstance(value, list) and any(
                str(item or "").strip()
                for item in value
            ):
                return True

        return False
