class CDSService:
    def get_checks(self, medical_note: str, encounter: dict | None = None) -> list[dict]:
        text = medical_note or ""
        checks = []

        def present(keywords: list[str]) -> bool:
            return any(k in text for k in keywords)

        def add(category, item, keywords, level="normal"):
            checks.append({
                "category": category,
                "item": item,
                "level": level,
                "checked": present(keywords),
            })

        if text.strip():
            add("共通", "アレルギー歴", ["アレルギー", "薬疹"], "important")
            add("共通", "内服薬", ["内服", "服薬", "薬"], "important")
            add("共通", "既往歴", ["既往", "糖尿病", "高血圧", "COPD", "喘息"], "normal")

        if present(["発熱", "熱", "37", "38", "39", "40"]):
            self._fever_checks(add)

        if present(["咳", "痰", "のど", "咽頭", "感冒", "鼻水"]):
            self._cough_checks(add)

        if present(["腹痛", "お腹", "腹部", "胃痛", "みぞおち"]):
            self._abdominal_pain_checks(add)

        return self._remove_duplicates(checks)

    def _fever_checks(self, add):
        add("発熱", "発熱期間", ["昨日", "今日", "日前", "時間前", "朝から"], "important")
        add("発熱", "最高体温", ["37", "38", "39", "40", "℃", "度"], "important")
        add("発熱", "悪寒・戦慄", ["悪寒", "寒気", "戦慄"], "normal")
        add("発熱", "咳・痰", ["咳", "痰"], "normal")
        add("発熱", "咽頭所見", ["咽頭", "のど", "喉", "発赤"], "important")
        add("発熱", "呼吸音", ["呼吸音", "ラ音", "wheeze", "crackle"], "important")
        add("発熱", "SpO2", ["SpO2", "サチュレーション", "酸素"], "important")
        add("発熱", "COVID検査", ["コロナ", "COVID"], "normal")
        add("発熱", "インフルエンザ検査", ["インフル"], "normal")
        add("発熱", "接触歴", ["接触", "周囲", "家族", "職場"], "normal")

    def _cough_checks(self, add):
        add("咳・感冒", "咳の期間", ["昨日", "今日", "日前", "週間", "朝から"], "important")
        add("咳・感冒", "痰の性状", ["痰", "黄色", "膿性", "透明"], "normal")
        add("咳・感冒", "喘鳴", ["喘鳴", "ゼーゼー", "ヒューヒュー"], "normal")
        add("咳・感冒", "呼吸音", ["呼吸音", "ラ音", "wheeze", "crackle"], "important")
        add("咳・感冒", "SpO2", ["SpO2", "サチュレーション", "酸素"], "important")
        add("咳・感冒", "喫煙歴", ["喫煙", "たばこ", "タバコ"], "normal")
        add("咳・感冒", "COPD・喘息の既往", ["COPD", "肺気腫", "喘息"], "normal")

    def _abdominal_pain_checks(self, add):
        add("腹痛", "痛みの部位", ["右下腹部", "心窩部", "みぞおち", "下腹部", "腹部"], "important")
        add("腹痛", "発症時刻・経過", ["昨日", "今日", "日前", "突然", "徐々に"], "important")
        add("腹痛", "嘔吐・悪心", ["嘔吐", "吐き気", "悪心"], "normal")
        add("腹痛", "下痢・血便", ["下痢", "血便", "黒色便"], "important")
        add("腹痛", "圧痛部位", ["圧痛", "押すと痛い"], "important")
        add("腹痛", "反跳痛・筋性防御", ["反跳痛", "筋性防御", "腹膜刺激"], "important")
        add("腹痛", "尿症状", ["排尿痛", "頻尿", "血尿"], "normal")
        add("腹痛", "腹部手術歴", ["手術歴", "虫垂炎", "胆摘", "胃切除"], "normal")

    def _remove_duplicates(self, checks):
        result = []
        seen = set()

        for check in checks:
            key = (check["category"], check["item"])
            if key not in seen:
                result.append(check)
                seen.add(key)

        return result