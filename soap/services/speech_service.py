import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .medical_dictionary_service import MedicalDictionaryService

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class SpeechService:
    def __init__(self):
        self.medical_dictionary = MedicalDictionaryService()

    def transcribe_audio(
        self,
        audio_file,
        intake_note: str = "",
        is_final: bool = False,
    ) -> str:
        """
        途中音声は医学用語プロンプト付きで高速文字起こしし、
        最終音声は話者分離モデルで会話全体を保持する。
        """
        file_bytes = audio_file.read()
        file_tuple = (
            audio_file.name,
            file_bytes,
            audio_file.content_type,
        )

        if is_final:
            text = self.transcribe_with_speakers(
                file_tuple
            )
        else:
            text = self.transcribe_realtime(
                file_tuple=file_tuple,
                intake_note=intake_note,
            )

        return self.medical_dictionary.correct(text)

    def transcribe_realtime(
        self,
        file_tuple,
        intake_note: str,
    ) -> str:
        prompt = self.medical_dictionary.build_transcription_prompt(
            intake_note
        )

        request_args = {
            "model": "gpt-4o-transcribe",
            "file": file_tuple,
            "language": "ja",
        }

        if prompt:
            request_args["prompt"] = prompt

        try:
            transcript = client.audio.transcriptions.create(
                **request_args
            )
        except TypeError:
            request_args.pop("prompt", None)
            transcript = client.audio.transcriptions.create(
                **request_args
            )

        return transcript.text

    def transcribe_with_speakers(
        self,
        file_tuple,
    ) -> str:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe-diarize",
            file=file_tuple,
            language="ja",
            response_format="diarized_json",
            chunking_strategy="auto",
        )

        segments = getattr(transcript, "segments", None)

        if not segments:
            return getattr(transcript, "text", "")

        return self.format_speaker_segments(segments)

    @staticmethod
    def format_speaker_segments(
        segments: list[Any],
    ) -> str:
        speaker_labels = {}
        lines = []

        for segment in segments:
            if isinstance(segment, dict):
                speaker = segment.get("speaker")
                text = segment.get("text", "")
            else:
                speaker = getattr(
                    segment,
                    "speaker",
                    None,
                )
                text = getattr(segment, "text", "")

            cleaned = str(text or "").strip()

            if not cleaned:
                continue

            speaker_key = str(
                speaker or "unknown"
            )

            if speaker_key not in speaker_labels:
                label_number = len(speaker_labels)
                label = (
                    chr(ord("A") + label_number)
                    if label_number < 26
                    else str(label_number + 1)
                )
                speaker_labels[speaker_key] = label

            lines.append(
                f"話者{speaker_labels[speaker_key]}：{cleaned}"
            )

        return "\n".join(lines)
