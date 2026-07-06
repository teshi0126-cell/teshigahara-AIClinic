import os
from dotenv import load_dotenv
from openai import OpenAI

# .envを読み込む
load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

response = client.responses.create(
    model="gpt-5.5",
    input="こんにちは。あなたは誰ですか？"
)

print(response.output_text)