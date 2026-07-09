from .openai_service import OpenAIService
from soap.prompts.referral_prompt import REFERRAL_SYSTEM_PROMPT


class ReferralService:
    def __init__(self):
        self.ai = OpenAIService()

    def create_referral(self, medical_note: str, encounter: dict) -> str:
        prompt = f"""
{REFERRAL_SYSTEM_PROMPT}

【診察メモ】
{medical_note}

【Encounter JSON】
{encounter}
"""
        return self.ai.generate_text(prompt)