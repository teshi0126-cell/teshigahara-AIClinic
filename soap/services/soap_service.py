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

        return self.remove_unsupported_confirmation_section(
            result,
            encounter,
        )

    @staticmethod
    def remove_unsupported_confirmation_section(
        soap_text: str,
        encounter: dict,
    ) -> str:
        """
        確認事項は診療支援チェックへ分離し、SOAP本文から削除する。
        """
        if encounter.get("missing_items"):
            return soap_text

        return re.split(
            r"\n\s*確認すべき点[：:]",
            soap_text,
            maxsplit=1,
        )[0].rstrip()
