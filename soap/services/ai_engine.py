import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AIEngine:
    def __init__(self, model: str = "gpt-5.5"):
        self.model = model

    def generate_text(self, prompt: str) -> str:
        response = client.responses.create(
            model=self.model,
            input=prompt,
        )
        return response.output_text