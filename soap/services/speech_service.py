import os

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
        音声を文字起こしする。

        is_final はリアルタイムチャンクと最終音声の呼び出し形式を
        統一するために受け取る。現時点ではAPI設定の分岐には使わない。
        """
        del is_final

        file_bytes = audio_file.read()
        prompt = self.medical_dictionary.build_transcription_prompt(
            intake_note
        )

        request_args = {
            "model": "gpt-4o-transcribe",
            "file": (
                audio_file.name,
                file_bytes,
                audio_file.content_type,
            ),
            "language": "ja",
        }

        if prompt:
            request_args["prompt"] = prompt

        try:
            transcript = client.audio.transcriptions.create(
                **request_args
            )
        except TypeError:
            # prompt未対応環境との後方互換
            request_args.pop("prompt", None)
            transcript = client.audio.transcriptions.create(
                **request_args
            )

        return self.medical_dictionary.correct(
            transcript.text
        )
