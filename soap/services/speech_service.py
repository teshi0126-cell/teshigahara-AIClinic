from openai import OpenAI
import os
from dotenv import load_dotenv

from .medical_dictionary_service import MedicalDictionaryService

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class SpeechService:
    def __init__(self):
        self.medical_dictionary = MedicalDictionaryService()

    def transcribe_audio(self, audio_file, intake_note: str = "") -> str:
        file_bytes = audio_file.read()
        prompt = self.medical_dictionary.build_transcription_prompt(intake_note)

        try:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=(audio_file.name, file_bytes, audio_file.content_type),
                language="ja",
                prompt=prompt,
            )
        except TypeError:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=(audio_file.name, file_bytes, audio_file.content_type),
                language="ja",
            )

        return self.medical_dictionary.correct(transcript.text)