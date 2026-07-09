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
            "SPO2": "SpO2",
            "spo2": "SpO2",
            "サチュレーション": "SpO2",
            "コロナ抗原は陰性": "コロナ抗原陰性",
            "コロナ抗原が陰性": "コロナ抗原陰性",
        }

        corrected = text

        for wrong, right in corrections.items():
            corrected = corrected.replace(wrong, right)

        return corrected