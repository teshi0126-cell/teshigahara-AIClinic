class ConversationService:
    def build_conversation_text(self, chunks: list[str]) -> str:
        if not chunks:
            return ""

        lines = []

        for index, text in enumerate(chunks, start=1):
            cleaned = (text or "").strip()
            if cleaned:
                lines.append(f"発話{index}：{cleaned}")

        return "\n".join(lines)

    def build_combined_note(
        self,
        intake_note: str,
        conversation_text: str,
        structured_conversation_text: str = ""
    ) -> str:
        return f"""
【受付問診】
{intake_note}

【音声文字起こし】
{conversation_text}

【役割推定済み会話】
{structured_conversation_text}
""".strip()