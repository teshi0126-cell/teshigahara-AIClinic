from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class SpeechService:
    def transcribe_audio(self, audio_file) -> str:
        file_bytes = audio_file.read()

        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=(audio_file.name, file_bytes, audio_file.content_type),
            language="ja",
        )

        return self.correct_medical_terms(transcript.text)

    def correct_medical_terms(self, text: str) -> str:
        corrections = {
            "イントーフォッセキ": "咽頭発赤",
            "いんとうほっせき": "咽頭発赤",
            "イントウホッセキ": "咽頭発赤",
            "咽頭宝石": "咽頭発赤",
            "咽頭発跡": "咽頭発赤",
            "咽頭発責": "咽頭発赤",

            "SPO2": "SpO2",
            "spo2": "SpO2",
            "エスピーオーツー": "SpO2",
            "サチュレーション": "SpO2",

            "コロナ抗原は陰性": "COVID抗原陰性",
            "コロナ抗原が陰性": "COVID抗原陰性",
            "コロナ抗原陰性": "COVID抗原陰性",
            "COVID-19抗原は陰性": "COVID抗原陰性",

            "カルナール": "カロナール",
            "カロナール処法": "カロナール処方",
            "カロナールを処方します": "カロナール処方",
            "カロナール出します": "カロナール処方",

            "水分をしっかり取ってください": "水分摂取指導",
            "水分をしっかり摂ってください": "水分摂取指導",
            "高熱が続く場合は再診してください": "高熱持続時再診指示",
        }

        corrected = text

        for wrong, right in corrections.items():
            corrected = corrected.replace(wrong, right)

        return corrected