# AIClinic 基本設計書

## 目的

AIClinicは、外来診療中の音声・診察メモをもとに、診療記録作成、診療支援、文書作成を補助するシステムである。

最終判断とカルテ記載責任は医師が行う。

---

## 基本方針

1. AIは診療記録の下書きを作成する。
2. AIは入力にない情報を追加しない。
3. 診断・処方・検査の最終判断は医師が行う。
4. 患者個人情報は必要最小限にする。
5. M3 DigiKarへの反映前に必ず医師が確認する。

---

## 全体構成

AIClinicは以下の機能群で構成する。

### 1. Speech Engine

音声入力を扱う。

- Jabra Speak2 75から音声取得
- ブラウザ録音
- 10秒ごとの分割音声送信
- gpt-4o-transcribeによる医学用語重視の全文文字起こし
- gpt-4o-transcribe-diarizeによる匿名話者境界の抽出
- 両結果を統合し、短い患者返答を保持
- 明確な質問・短答がある単一話者結果だけを保守的に再分離
- 発言内容が変化した再分離結果は破棄
- 複数話者が単一話者へ潰れた場合は話者分離版へ戻す
- 話者分離に失敗しても全文文字起こしとSOAP生成を継続

### 2. Encounter Engine

診療内容を構造化する中核。

- 診察メモ
- 文字起こし
- 主訴
- 現病歴
- 自覚症状
- バイタル
- 身体所見
- 検査結果
- 評価
- 方針
- 確認不足項目

### 3. SOAP Engine

Encounter JSONからSOAPを生成する。

- S：患者の訴え
- O：所見・検査・バイタル
- A：医師判断補助
- P：記載された方針のみ

### 4. Clinical Decision Support

診療漏れを補助する。

例：

- SpO2未確認
- アレルギー未確認
- 喫煙歴未確認
- 発熱時の確認項目
- 胸痛時の確認項目
- 腹痛時の確認項目

### 5. Document Generator

Encounter JSONから文書を作成する。

- 紹介状
- 患者説明文
- 診断書下書き
- 健診結果説明
- 返書
- 英文紹介状

### 6. DigiKar Connector

M3 DigiKarへの反映を補助する。

初期段階：

- SOAPをコピー
- 手動貼り付け

将来：

- 自動貼り付け支援
- 連携可能性調査

---

## データの流れ

```text
Jabra Speak2 75
    ↓
ブラウザ録音
    ↓
Speech Engine
    ↓
文字起こし
    ↓
Encounter Engine
    ↓
Encounter JSON
    ↓
SOAP Engine
    ↓
SOAP
    ↓
医師確認
    ↓
M3 DigiKarへ貼付

## Encounter JSON

AIClinicの中心データ。

```json
{
  "chief_complaint": null,
  "history": [],
  "subjective_symptoms": [],
  "vital_signs": {
    "temperature": null,
    "blood_pressure": null,
    "pulse": null,
    "spo2": null
  },
  "physical_exam": [],
  "tests": [],
  "assessment": [],
  "plan": [],
  "missing_items": []
}