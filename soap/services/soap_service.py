import json
import re

from .openai_service import OpenAIService
from .encounter_service import EncounterService
from soap.prompts.soap_prompt import SOAP_SYSTEM_PROMPT


class SOAPService:
    def __init__(self):
        self.ai = OpenAIService()
        self.encounter_service = EncounterService()

    def create_soap(self, medical_note: str) -> str:
        encounter = self.encounter_service.create_encounter_json(
            medical_note
        )
        return self.create_soap_from_encounter(encounter)

    def create_soap_from_encounter(self, encounter: dict) -> str:
        """
        生成済みEncounter JSONからSOAPを作成する。

        Encounterを再生成しないため、API呼び出しの重複と
        出力間の不整合を防ぐ。
        """
        encounter_json = json.dumps(
            encounter,
            ensure_ascii=False,
            indent=2,
        )

        prompt = f"""
{SOAP_SYSTEM_PROMPT}

以下は診察メモから作成した構造化診療データです。
このJSONだけを根拠にSOAPを作成してください。
JSONにない情報は追加しないでください。

【Encounter JSON】
{encounter_json}
"""
        result = self.ai.generate_text(prompt)

        result = self.remove_unsupported_confirmation_section(
            result,
            encounter,
        )

        result = self.remove_unsupported_plan_actions(
            result,
            encounter,
        )

        result = self.remove_inferred_exam_actions(
            result,
            encounter,
        )

        result = self.remove_duplicate_bullets(
            result
        )

        return self.remove_empty_bullets(
            result
        )

    @staticmethod
    def remove_unsupported_plan_actions(
        soap_text: str,
        encounter: dict,
    ) -> str:
        """
        原文由来のEncounterに存在しない医療行為をPから除外する。
        """
        encounter_text = json.dumps(
            encounter,
            ensure_ascii=False,
        )

        guarded_actions = (
            "経過観察",
            "再診",
            "検査",
            "紹介",
            "処方",
            "中止",
            "増量",
            "減量",
        )

        lines = []

        for line in soap_text.splitlines():
            stripped = line.strip()

            unsupported = any(
                action in stripped
                and action not in encounter_text
                for action in guarded_actions
            )

            if not unsupported:
                lines.append(line)

        return "\n".join(lines).rstrip()

    @staticmethod
    def remove_inferred_exam_actions(
        soap_text: str,
        encounter: dict,
    ) -> str:
        """
        診察中の声かけから推定された診察行為をPから除外する。

        例：「音を聞かせて」だけを根拠に
        「聴診を行う」という計画を作らない。
        """
        encounter_section = encounter.get(
            "encounter",
            {},
        )

        if not isinstance(encounter_section, dict):
            encounter_section = {}

        intake_section = encounter.get(
            "intake",
            {},
        )

        if not isinstance(intake_section, dict):
            intake_section = {}

        source_text = " ".join(
            [
                str(
                    encounter_section.get(
                        "raw_text",
                        "",
                    )
                    or ""
                ),
                str(
                    intake_section.get(
                        "raw_text",
                        "",
                    )
                    or ""
                ),
            ]
        )

        exam_actions = (
            "聴診",
            "触診",
            "打診",
            "視診",
        )

        lines = []
        current_section = ""

        for line in soap_text.splitlines():
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

            inferred_exam = (
                current_section == "P"
                and any(
                    action in stripped
                    and action not in source_text
                    for action in exam_actions
                )
            )

            if not inferred_exam:
                lines.append(line)

        return "\n".join(lines).rstrip()

    @staticmethod
    def remove_duplicate_bullets(
        soap_text: str,
    ) -> str:
        """
        同一セクション内の完全重複した箇条書きを除外する。
        """
        lines = []
        seen_by_section = {}
        current_section = ""

        for line in soap_text.splitlines():
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
                seen_by_section.setdefault(
                    current_section,
                    set(),
                )
                lines.append(line)
                continue

            if stripped.startswith(("-", "・")):
                normalized = re.sub(
                    r"[\s。．、，]",
                    "",
                    stripped.lstrip("-・").strip(),
                )

                if normalized:
                    seen = seen_by_section.setdefault(
                        current_section,
                        set(),
                    )

                    if normalized in seen:
                        continue

                    seen.add(normalized)

            lines.append(line)

        return "\n".join(lines).rstrip()

    @staticmethod
    def remove_empty_bullets(
        soap_text: str,
    ) -> str:
        """
        「O：\n-」のような内容のない箇条書きを除外する。
        """
        lines = [
            line
            for line in soap_text.splitlines()
            if line.strip() not in {"-", "・"}
        ]

        return "\n".join(lines).rstrip()

    @staticmethod
    def remove_unsupported_confirmation_section(
        soap_text: str,
        encounter: dict,
    ) -> str:
        """
        確認事項は診療支援チェックへ分離し、SOAP本文から削除する。
        """
        return re.split(
            r"\n\s*確認すべき点[：:]",
            soap_text,
            maxsplit=1,
        )[0].rstrip()
