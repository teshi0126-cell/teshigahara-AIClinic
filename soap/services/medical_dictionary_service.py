import csv
from pathlib import Path


class MedicalDictionaryService:
    def __init__(self):
        self.dictionary_path = (
            Path(__file__).resolve().parent.parent / "data" / "medical_dictionary.csv"
        )
        self.corrections = self.load_dictionary()

    def load_dictionary(self) -> dict[str, str]:
        corrections = {}

        if not self.dictionary_path.exists():
            return corrections

        with open(self.dictionary_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                wrong = (row.get("wrong") or "").strip()
                right = (row.get("right") or "").strip()

                if wrong and right:
                    corrections[wrong] = right

        return corrections

    def correct(self, text: str) -> str:
        corrected = text or ""

        for wrong, right in self.corrections.items():
            corrected = corrected.replace(wrong, right)

        return corrected

    def build_transcription_prompt(self) -> str:
        terms = sorted(set(self.corrections.values()))

        if not terms:
            return ""

        selected_terms = terms[:200]

        return (
            "これは日本の外来診療の音声です。"
            "以下の医学用語が頻出します。"
            "可能な限り正確に文字起こししてください。\n"
            + "\n".join(selected_terms)
        )