from .ai_engine import AIEngine
from .encounter_service import EncounterService
from soap.prompts.soap_prompt import SOAP_SYSTEM_PROMPT


class SOAPService:
    def __init__(self):
        self.ai = AIEngine()
        self.encounter_service = EncounterService()

    def create_soap(self, medical_note: str) -> str:
        encounter = self.encounter_service.create_encounter_json(medical_note)

        prompt = f"""
{SOAP_SYSTEM_PROMPT}

以下は診察メモから作成した構造化診療データです。
このJSONだけを根拠にSOAPを作成してください。
JSONにない情報は追加しないでください。

【Encounter JSON】
{encounter}
"""
        return self.ai.generate_text(prompt)