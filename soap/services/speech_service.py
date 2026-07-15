import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .medical_dictionary_service import MedicalDictionaryService

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)


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
        途中音声は医学用語プロンプト付きで高速文字起こしする。

        最終音声は医療語を重視した全文認識と話者分離を
        独立して行い、両方が成功した場合だけ統合する。
        一方が失敗しても成功した結果を返す。
        """
        file_bytes = audio_file.read()
        file_tuple = (
            audio_file.name,
            file_bytes,
            audio_file.content_type,
        )

        if is_final:
            text = self.transcribe_final(
                file_tuple=file_tuple,
                intake_note=intake_note,
            )
        else:
            text = self.transcribe_realtime(
                file_tuple=file_tuple,
                intake_note=intake_note,
            )

        return self.medical_dictionary.correct(text)

    def transcribe_final(
        self,
        file_tuple,
        intake_note: str,
    ) -> str:
        accurate_text = ""
        diarized_text = ""
        accurate_error = None
        diarized_error = None

        try:
            accurate_text = self.transcribe_realtime(
                file_tuple=file_tuple,
                intake_note=intake_note,
            )
        except Exception as exc:
            accurate_error = exc
            logger.error(
                "Prompted final transcription failed"
            )

        try:
            diarized_text = self.transcribe_with_speakers(
                file_tuple
            )
        except Exception as exc:
            diarized_error = exc
            logger.error(
                "Speaker diarization failed"
            )

        accurate_text = (accurate_text or "").strip()
        diarized_text = (diarized_text or "").strip()

        if accurate_text and diarized_text:
            try:
                merged = self.merge_accurate_and_diarized(
                    accurate_text=accurate_text,
                    diarized_text=diarized_text,
                    intake_note=intake_note,
                )
            except Exception:
                logger.error(
                    "Transcript reconciliation failed"
                )
                merged = ""

            # 語句精度を優先し、統合失敗時は全文認識へ戻す。
            return merged or accurate_text

        if accurate_text:
            return accurate_text

        if diarized_text:
            return diarized_text

        if accurate_error is not None:
            raise accurate_error

        if diarized_error is not None:
            raise diarized_error

        return ""

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

    def merge_accurate_and_diarized(
        self,
        accurate_text: str,
        diarized_text: str,
        intake_note: str = "",
    ) -> str:
        """
        全文認識を語句の基準、diarizationを話者境界の基準として
        文字起こしを統合する。音声にない診療情報の追加は禁止する。
        """
        prompt = f"""
あなたは日本の外来診療音声の文字起こし整形器です。
以下の2つは同じ録音から作られています。

【絶対ルール】
- 「高精度全文」を医学用語・数値・発言内容の主な根拠にする。
- 「話者分離版」は話者交代と短い返答を確認するためだけに使う。
- どちらにも存在しない症状、診断、検査値、薬剤、計画を追加しない。
- 聞き取れない語句を医学的に推測しない。必要なら［聞き取り不明］とする。
- 短い返答（はい、いいえ、そうです等）も削除しない。
- 話者の職種や関係を推測せず、話者A、話者Bの表記を維持する。
- 各行を必ず「話者A：」等で開始する。
- 解説、要約、Markdown、コードブロックは出力しない。

【受付問診（参考情報。発言として追加しない）】
{intake_note}

【高精度全文】
{accurate_text}

【話者分離版】
{diarized_text}

上記だけを根拠に、話者別の最終文字起こしを出力してください。
""".strip()

        response = client.responses.create(
            model=os.getenv(
                "OPENAI_TEXT_MODEL",
                "gpt-5.5",
            ),
            input=prompt,
        )

        output_text = getattr(
            response,
            "output_text",
            "",
        )

        return self.clean_merged_transcript(
            output_text
        )

    @staticmethod
    def clean_merged_transcript(text: str) -> str:
        cleaned = (text or "").strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            cleaned = "\n".join(lines).strip()

        lines = [
            line.strip()
            for line in cleaned.splitlines()
            if line.strip()
        ]

        if not lines:
            return ""

        if not all(
            line.startswith("話者")
            and ("：" in line or ":" in line)
            for line in lines
        ):
            return ""

        return "\n".join(lines)

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
