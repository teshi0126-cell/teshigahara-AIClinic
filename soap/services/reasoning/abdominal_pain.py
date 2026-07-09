def evaluate(medical_note: str, encounter: dict | None = None) -> list[dict]:
    text = medical_note or ""
    diagnoses = []

    has_abdominal_pain = any(w in text for w in ["腹痛", "お腹", "腹部", "胃痛", "みぞおち"])
    has_diarrhea = "下痢" in text
    has_vomiting = any(w in text for w in ["嘔吐", "吐き気", "悪心"])
    has_fever = any(w in text for w in ["発熱", "熱", "37", "38", "39", "40"])
    has_rlq = any(w in text for w in ["右下腹部", "右下腹"])
    has_rebound = any(w in text for w in ["反跳痛", "筋性防御", "腹膜刺激"])

    if not has_abdominal_pain:
        return diagnoses

    if has_diarrhea or has_vomiting:
        diagnoses.append({
            "name": "急性胃腸炎",
            "score": 75,
            "reasons": ["腹痛", "下痢または嘔吐"],
        })

    if has_rlq or has_rebound or has_fever:
        diagnoses.append({
            "name": "虫垂炎",
            "score": 60,
            "reasons": ["腹痛", "右下腹部痛・発熱・腹膜刺激の確認が重要"],
        })

    diagnoses.append({
        "name": "尿路結石・尿路感染症",
        "score": 35,
        "reasons": ["腹痛", "尿症状の確認が必要"],
    })

    return diagnoses