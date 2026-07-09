from .openai_service import OpenAIService
from soap.prompts.incremental_soap_prompt import INCREMENTAL_SOAP_PROMPT


class IncrementalSOAPService:
    def __init__(self):
        self.ai = OpenAIService()

    def update_soap(self, current_soap: str, combined_note: str) -> str:
        prompt = f"""
{INCREMENTAL_SOAP_PROMPT}

【現在のSOAP】
{current_soap}

【新たに得られた診療情報】
{combined_note}
"""
        return self.ai.generate_text(prompt)