class ConversationService:
    def build_conversation_text(self, chunks: list[str]) -> str:
        """
        音声文字起こしチャンクを時系列の会話ログとして整形する。
        現時点では話者分離はせず、順番を保持する。
        """
        if not chunks:
            return ""

        lines = []

        for index, text in enumerate(chunks, start=1):
            cleaned = (text or "").strip()
            if cleaned:
                lines.append(f"{index}. {cleaned}")

        return "\n".join(lines)

    def build_combined_note(self, intake_note: str, conversation_text: str) -> str:
        """
        受付問診と診察中会話を統合してAIに渡すテキストを作る。
        """
        return f"""
【受付問診】
{intake_note}

【診察中の会話・音声文字起こし】
{conversation_text}
""".strip()