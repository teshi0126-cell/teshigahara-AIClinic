def evaluate(medical_note: str, encounter: dict | None = None) -> list[dict]:
    text = medical_note or ""
    diagnoses = []

    has_fever = any(w in text for w in ["発熱", "熱", "37", "38", "39", "40"])
    has_cough = "咳" in text
    has_throat = any(w in text for w in ["咽頭", "のど", "喉", "発赤"])
    has_covid_test = any(w in text for w in ["コロナ", "COVID"])
    has_influenza = "インフル" in text
    has_spo2 = any(w in text for w in ["SpO2", "サチュレーション", "酸素"])

    if not has_fever:
        return diagnoses

    if has_fever and (has_cough or has_throat):
        diagnoses.append({
            "name": "ウイルス性上気道炎",
            "score": 80,
            "reasons": ["発熱", "咳または咽頭症状"],
        })

    if has_fever and has_cough:
        diagnoses.append({
            "name": "COVID-19",
            "score": 70 if not has_covid_test else 50,
            "reasons": ["発熱", "咳", "COVID検査の確認が必要"],
        })

    if has_fever:
        diagnoses.append({
            "name": "インフルエンザ",
            "score": 65 if not has_influenza else 45,
            "reasons": ["発熱", "急性発症の可能性"],
        })

    if has_fever and has_cough:
        diagnoses.append({
            "name": "肺炎",
            "score": 45 if has_spo2 else 55,
            "reasons": ["発熱", "咳", "呼吸音・SpO2の確認が重要"],
        })

    if has_fever and not has_cough and not has_throat:
        diagnoses.append({
            "name": "尿路感染症",
            "score": 35,
            "reasons": ["発熱", "呼吸器症状が乏しい場合は鑑別"],
        })

    return diagnoses