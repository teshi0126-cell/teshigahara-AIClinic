class CDSService:
    def get_checks(self, medical_note: str, encounter: dict | None = None) -> list[dict]:
        text = medical_note or ""
        checks = []

        def is_present(keywords: list[str]) -> bool:
            return any(word in text for word in keywords)

        def add(category: str, item: str, keywords: list[str], level: str = "normal"):
            checked = is_present(keywords)
            checks.append({
                "category": category,
                "item": item,
                "level": level,
                "checked": checked,
            })

        if text.strip():
            add("共通", "アレルギー歴", ["アレルギー", "薬疹"], "important")
            add("共通", "内服薬", ["内服", "薬", "服薬"], "important")
            add("共通", "既往歴", ["既往", "糖尿病", "高血圧", "COPD", "喘息"], "normal")

        if is_present(["発熱", "熱", "37", "38", "39", "40"]):
            add("発熱", "発熱期間", ["昨日", "今日", "日前", "時間前", "朝から"], "important")
            add("発熱", "最高体温", ["37", "38", "39", "40", "℃", "度"], "important")
            add("発熱", "悪寒・戦慄", ["悪寒", "寒気", "戦慄"], "normal")
            add("発熱", "咳・痰", ["咳", "痰"], "normal")
            add("発熱", "咽頭痛", ["咽頭痛", "のど", "喉"], "normal")
            add("発熱", "呼吸困難", ["息苦しい", "呼吸困難", "息切れ"], "important")
            add("発熱", "SpO2", ["SpO2", "サチュレーション", "酸素"], "important")
            add("発熱", "COVID検査", ["コロナ", "COVID"], "normal")
            add("発熱", "インフルエンザ検査", ["インフル"], "normal")
            add("発熱", "接触歴", ["接触", "周囲", "家族", "職場"], "normal")

        if is_present(["咳", "痰", "のど", "咽頭", "感冒", "鼻水", "鼻汁"]):
            add("咳・感冒", "咳の期間", ["昨日", "今日", "日前", "週間", "朝から"], "important")
            add("咳・感冒", "痰の性状", ["痰", "黄色", "膿性", "透明"], "normal")
            add("咳・感冒", "喘鳴", ["喘鳴", "ゼーゼー", "ヒューヒュー"], "normal")
            add("咳・感冒", "呼吸音", ["呼吸音", "ラ音", "wheeze", "crackle"], "important")
            add("咳・感冒", "SpO2", ["SpO2", "サチュレーション", "酸素"], "important")
            add("咳・感冒", "喫煙歴", ["喫煙", "たばこ", "タバコ"], "normal")
            add("咳・感冒", "COPD・喘息の既往", ["COPD", "肺気腫", "喘息"], "normal")

        if is_present(["腹痛", "お腹", "腹部", "胃痛", "みぞおち"]):
            add("腹痛", "痛みの部位", ["右下腹部", "心窩部", "みぞおち", "下腹部", "腹部"], "important")
            add("腹痛", "発症時刻・経過", ["昨日", "今日", "日前", "突然", "徐々に"], "important")
            add("腹痛", "嘔吐", ["嘔吐", "吐き気", "悪心"], "normal")
            add("腹痛", "下痢・血便", ["下痢", "血便", "黒色便"], "important")
            add("腹痛", "圧痛部位", ["圧痛", "押すと痛い"], "important")
            add("腹痛", "反跳痛・筋性防御", ["反跳痛", "筋性防御", "腹膜刺激"], "important")
            add("腹痛", "尿症状", ["排尿痛", "頻尿", "血尿"], "normal")
            add("腹痛", "腹部手術歴", ["手術歴", "虫垂炎", "胆摘", "胃切除"], "normal")

        if is_present(["胸痛", "胸が痛", "胸部痛", "胸苦", "胸が苦"]):
            add("胸痛", "発症時刻", ["時から", "分前", "時間前", "突然"], "important")
            add("胸痛", "持続時間", ["分", "時間", "持続"], "important")
            add("胸痛", "放散痛", ["放散", "左肩", "顎", "背中"], "important")
            add("胸痛", "冷汗", ["冷汗", "汗"], "important")
            add("胸痛", "呼吸困難", ["息苦しい", "呼吸困難", "息切れ"], "important")
            add("胸痛", "SpO2", ["SpO2", "サチュレーション", "酸素"], "important")
            add("胸痛", "心電図", ["心電図", "ECG"], "important")
            add("胸痛", "冠危険因子", ["糖尿病", "高血圧", "脂質異常", "喫煙"], "normal")

        return checks