from .ai_engine import AIEngine
from soap.prompts.soap_prompt import SOAP_SYSTEM_PROMPT


class SOAPService:
    def __init__(self):
        self.ai = AIEngine()

    def create_soap(self, medical_note: str) -> str:
        prompt = f"""
{SOAP_SYSTEM_PROMPT}

【診察メモ】
{medical_note}
"""
        return self.ai.generate_text(prompt)