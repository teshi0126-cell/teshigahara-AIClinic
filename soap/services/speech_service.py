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

        return transcript.text