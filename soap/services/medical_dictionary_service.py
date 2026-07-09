import csv
from pathlib import Path


class MedicalDictionaryService:
    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent / "data"

        self.local_dictionary_path = base_dir / "medical_dictionary.csv"
        self.external_dictionary_dir = base_dir / "external"

        self.corrections = self.load_local_dictionary()
        self.medical_terms = self.load_external_terms()

    def load_local_dictionary(self) -> dict[str, str]:
        corrections = {}

        if not self.local_dictionary_path.exists():
            return corrections

        with open(self.local_dictionary_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                wrong = (row.get("wrong") or "").strip()
                right = (row.get("right") or "").strip()

                if wrong and right:
                    corrections[wrong] = right

        return corrections

    def load_external_terms(self) -> set[str]:
        terms = set()

        if not self.external_dictionary_dir.exists():
            return terms

        for path in self.external_dictionary_dir.glob("*.csv"):
            terms.update(self.extract_terms_from_csv(path))

        return terms

    def extract_terms_from_csv(self, path: Path) -> set[str]:
        terms = set()

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    for value in row.values():
                        text = (value or "").strip()

                        if self.is_usable_medical_term(text):
                            terms.add(text)

        except Exception:
            return terms

        return terms

    def is_usable_medical_term(self, text: str) -> bool:
        if not text:
            return False

        if len(text) < 2:
            return False

        if len(text) > 40:
            return False

        blocked = [
            "コード",
            "番号",
            "更新",
            "廃止",
            "分類",
            "備考",
        ]

        if text in blocked:
            return False

        return True

    def correct(self, text: str) -> str:
        corrected = text or ""

        for wrong, right in self.corrections.items():
            corrected = corrected.replace(wrong, right)

        return corrected

    def build_transcription_prompt(self, intake_note: str = "") -> str:
        terms = set(self.corrections.values())
        terms.update(self.medical_terms)

        prioritized_terms = self.prioritize_terms(terms, intake_note)

        if not prioritized_terms:
            return ""

        selected_terms = prioritized_terms[:300]

        return (
            "これは日本の外来診療の音声です。"
            "以下の医学用語・薬剤名・検査名が出る可能性があります。"
            "可能な限り正確に文字起こししてください。\n"
            + "\n".join(selected_terms)
        )

    def prioritize_terms(self, terms: set[str], intake_note: str = "") -> list[str]:
        intake = intake_note or ""

        priority_keywords = []

        if any(word in intake for word in ["発熱", "熱", "咳", "のど", "咽頭"]):
            priority_keywords.extend([
                "咽頭発赤",
                "扁桃腫大",
                "膿栓",
                "SpO2",
                "COVID",
                "COVID抗原",
                "インフルエンザ",
                "カロナール",
                "アセトアミノフェン",
                "急性上気道炎",
                "急性咽頭炎",
            ])

        if any(word in intake for word in ["腹痛", "お腹", "下痢", "嘔吐"]):
            priority_keywords.extend([
                "急性胃腸炎",
                "虫垂炎",
                "胆嚢炎",
                "膵炎",
                "尿管結石",
                "圧痛",
                "反跳痛",
                "筋性防御",
            ])

        if any(word in intake for word in ["むくみ", "浮腫", "腫れ"]):
            priority_keywords.extend([
                "下腿浮腫",
                "圧痕",
                "DVT",
                "深部静脈血栓症",
                "リンパ浮腫",
                "静脈瘤",
                "心不全",
                "BNP",
                "Dダイマー",
                "Alb",
            ])

        ordered = []

        for term in priority_keywords:
            if term in terms or term:
                ordered.append(term)

        remaining = sorted(terms)

        for term in remaining:
            if term not in ordered:
                ordered.append(term)

        return ordered