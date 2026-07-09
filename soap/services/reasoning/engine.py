from . import fever, cough, abdominal_pain


class ClinicalReasoningEngine:
    def evaluate(self, medical_note: str, encounter: dict | None = None) -> list[dict]:
        diagnoses = []

        diagnoses += fever.evaluate(medical_note, encounter)
        diagnoses += cough.evaluate(medical_note, encounter)
        diagnoses += abdominal_pain.evaluate(medical_note, encounter)

        diagnoses = self._merge_diagnoses(diagnoses)
        diagnoses.sort(key=lambda x: x["score"], reverse=True)

        return diagnoses[:8]

    def _merge_diagnoses(self, diagnoses: list[dict]) -> list[dict]:
        merged = {}

        for dx in diagnoses:
            name = dx["name"]

            if name not in merged:
                merged[name] = dx
            else:
                merged[name]["score"] = max(merged[name]["score"], dx["score"])
                merged[name]["reasons"] = list(
                    set(merged[name]["reasons"] + dx["reasons"])
                )

        return list(merged.values())