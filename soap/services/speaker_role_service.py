import json
from .openai_service import OpenAIService
from soap.prompts.speaker_role_prompt import SPEAKER_ROLE_SYSTEM_PROMPT


class SpeakerRoleService:
    def __init__(self):
        self.ai = OpenAIService()

    def structure_conversation(self, conversation_text: str) -> list[dict]:
        if not conversation_text.strip():
            return []

        prompt = f"""
{SPEAKER_ROLE_SYSTEM_PROMPT}

【音声文字起こし】
{conversation_text}
"""

        result = self.ai.generate_text(prompt)

        try:
            data = json.loads(result)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return [
                {
                    "speaker_role": "unknown",
                    "text": conversation_text
                }
            ]

    def to_text(self, structured_items: list[dict]) -> str:
        label_map = {
            "doctor": "医師",
            "patient": "患者",
            "family": "家族",
            "nurse": "看護師",
            "unknown": "不明",
        }

        lines = []
        for item in structured_items:
            role = item.get("speaker_role", "unknown")
            text = item.get("text", "")
            label = label_map.get(role, "不明")
            lines.append(f"{label}：{text}")

        return "\n".join(lines)