def evaluate(medical_note: str, encounter: dict | None = None) -> list[dict]:
    text = medical_note or ""
    diagnoses = []

    has_cough = "咳" in text
    has_sputum = "痰" in text
    has_wheeze = any(w in text for w in ["喘鳴", "ゼーゼー", "ヒューヒュー"])
    has_fever = any(w in text for w in ["発熱", "熱", "37", "38", "39", "40"])
    has_spo2 = any(w in text for w in ["SpO2", "サチュレーション", "酸素"])

    if not has_cough:
        return diagnoses

    diagnoses.append({
        "name": "急性気管支炎・感冒",
        "score": 70,
        "reasons": ["咳"],
    })

    if has_fever:
        diagnoses.append({
            "name": "肺炎",
            "score": 55 if has_spo2 else 65,
            "reasons": ["咳", "発熱", "SpO2・呼吸音の確認が重要"],
        })

    if has_wheeze:
        diagnoses.append({
            "name": "気管支喘息発作",
            "score": 70,
            "reasons": ["咳", "喘鳴"],
        })

    if has_sputum:
        diagnoses.append({
            "name": "細菌性気道感染症",
            "score": 45,
            "reasons": ["咳", "痰"],
        })

    return diagnoses