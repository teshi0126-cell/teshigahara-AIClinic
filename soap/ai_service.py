import os
from dotenv import load_dotenv
from openai import OpenAI
from .prompts import SOAP_SYSTEM_PROMPT

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def create_soap(medical_note: str) -> str:
    prompt = f"""
{SOAP_SYSTEM_PROMPT}

【診察メモ】
{medical_note}
"""

    response = client.responses.create(
        model="gpt-5.5",
        input=prompt,
    )

    return response.output_text