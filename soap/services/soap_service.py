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

        result = self.remove_report_narration(
            result
        )

        result = self.remove_duplicate_bullets(
            result
        )

        result = (
            self.remove_objective_assessment_duplicates(
                result
            )
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
    def remove_report_narration(
        soap_text: str,
    ) -> str:
        """
        「患者が回答」「医師発言あり」という
        SOAPとして不要な報告枠を事実表現へ整える。
        """
        lines = []

        for line in soap_text.splitlines():
            stripped = line.strip()

            if not stripped.startswith(("-", "・")):
                lines.append(line)
                continue

            prefix = line[: len(line) - len(line.lstrip())]
            bullet = stripped[0]
            content = stripped[1:].strip()
            original = content

            content = re.sub(
                r"(との?)?医師(?:の)?発言あり[。．]?$",
                "",
                content,
            )

            content = re.sub(
                r"と回答(?:した)?[。．]?$",
                "",
                content,
            )

            content = content.rstrip(
                "。．、， "
            )

            if content and content != original:
                lines.append(
                    f"{prefix}{bullet} {content}。"
                )
            else:
                lines.append(line)

        return "\n".join(lines).rstrip()

    @staticmethod
    def normalize_for_oa_comparison(
        text: str,
    ) -> str:
        """
        OとAの重複判定専用の保守的な正規化。

        「高血圧症」という診断は変換せず、
        今回の血圧が高いという観察表現だけを揃える。
        """
        normalized = (
            (text or "")
            .strip()
            .lstrip("-・")
            .strip()
        )

        normalized = re.sub(
            r"^(医師|担当医)[はが、\s]*",
            "",
            normalized,
        )

        normalized = re.sub(
            r"(と)?(述べている|述べた|"
            r"説明している|説明した)[。．]?$",
            "",
            normalized,
        )

        normalized = re.sub(
            r"(本日(?:は|の)?|今日は|今日)",
            "",
            normalized,
        )

        normalized = re.sub(
            r"(かなり|非常に|えらい)",
            "",
            normalized,
        )

        normalized = re.sub(
            r"血圧[がは]?(?:だいぶ|とても)?高い",
            "血圧高値",
            normalized,
        )

        return re.sub(
            r"[\s。．、，]",
            "",
            normalized,
        )

    @staticmethod
    def remove_objective_assessment_duplicates(
        soap_text: str,
    ) -> str:
        """
        AがOと同一文のコピーだけなら、A側の重複を除外する。

        「血圧高値。降圧不十分」など解釈が加わったAは残す。
        """
        objective_items = set()
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
                continue

            if (
                current_section == "O"
                and stripped.startswith(("-", "・"))
            ):
                normalized = (
                    SOAPService.normalize_for_oa_comparison(
                        stripped
                    )
                )

                if normalized:
                    objective_items.add(normalized)

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
                lines.append(line)
                continue

            duplicate = False

            if (
                current_section == "A"
                and stripped.startswith(("-", "・"))
            ):
                normalized = (
                    SOAPService.normalize_for_oa_comparison(
                        stripped
                    )
                )
                duplicate = (
                    bool(normalized)
                    and normalized in objective_items
                )

            if not duplicate:
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
