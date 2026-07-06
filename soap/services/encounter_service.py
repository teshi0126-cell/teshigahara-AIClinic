import json
from .ai_engine import AIEngine
from soap.prompts.encounter_prompt import ENCOUNTER_SYSTEM_PROMPT


class EncounterService:
    def __init__(self):
        self.ai = AIEngine()

    def create_encounter_json(self, medical_note: str) -> dict:
        prompt = f"""
{ENCOUNTER_SYSTEM_PROMPT}

【診察メモ】
{medical_note}
"""
        result_text = self.ai.generate_text(prompt)

        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            return {
                "error": "AIのJSON変換に失敗しました。",
                "raw_output": result_text
            }