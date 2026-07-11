import os

from dotenv import load_dotenv
from openai import OpenAI


def main():
    """
    OpenAI APIの接続を手動確認するためのスクリプト。

    Djangoのテスト探索でimportされてもAPIを呼び出さない。
    """
    load_dotenv()

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY")
    )

    response = client.responses.create(
        model="gpt-5.5",
        input="こんにちは。あなたは誰ですか？",
    )

    print(response.output_text)


if __name__ == "__main__":
    main()
