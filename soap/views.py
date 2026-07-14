import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .services.soap_service import SOAPService
from .services.incremental_soap_service import IncrementalSOAPService
from .services.encounter_service import EncounterService
from .services.speech_service import SpeechService
from .services.cds_service import CDSService
from .services.reasoning.engine import ClinicalReasoningEngine
from .services.referral_service import ReferralService
from .services.conversation_service import ConversationService
from .services.visit_analyzer_service import VisitAnalyzerService
from .services.clinical_record_validator import ClinicalRecordValidator

logger = logging.getLogger(__name__)


def build_medical_note(
    intake_note: str,
    encounter_note: str,
) -> str:
    """
    受付問診と診察会話を、空欄を除いて結合する。
    """
    sections = []

    intake = (intake_note or "").strip()
    encounter = (encounter_note or "").strip()

    if intake:
        sections.append(
            f"""【受付問診】
{intake}"""
        )

    if encounter:
        sections.append(
            f"""【診察メモ・音声文字起こし】
{encounter}"""
        )

    return "\n\n".join(sections).strip()


def parse_conversation_chunks(
    raw_value: str,
) -> list[str]:
    """
    JavaScriptから送られる会話チャンクJSONを安全に読み込む。
    """
    if not raw_value:
        return []

    try:
        parsed = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    chunks = []

    for item in parsed:
        text = str(item or "").strip()

        if text:
            chunks.append(text)

    return chunks


def build_source_data_from_request(request):
    """
    requestから受付問診・診察会話・会話チャンクを取得する。

    話者推定AIはここでは使用しない。
    余分なAPI呼び出しと誤推定を避けるため、
    文字起こし全文をVisit Analyzerへ直接渡す。
    """
    intake_note = request.POST.get(
        "intake_note",
        "",
    ).strip()

    encounter_note = request.POST.get(
        "medical_note",
        "",
    ).strip()

    conversation_chunks = parse_conversation_chunks(
        request.POST.get(
            "conversation_chunks",
            "",
        )
    )

    if conversation_chunks:
        conversation_service = ConversationService()

        conversation_text = (
            conversation_service.build_conversation_text(
                conversation_chunks
            )
        )
    else:
        conversation_text = encounter_note

    combined_note = build_medical_note(
        intake_note=intake_note,
        encounter_note=conversation_text,
    )

    return {
        "intake_note": intake_note,
        "encounter_note": encounter_note,
        "conversation_chunks": conversation_chunks,
        "conversation_text": conversation_text,
        "combined_note": combined_note,
    }


def analyze_visit(
    intake_note: str,
    conversation_text: str,
) -> dict:
    """
    診療タイプとProblem Listを抽出する。
    """
    analyzer = VisitAnalyzerService()

    return analyzer.analyze(
        intake_note=intake_note,
        conversation_text=conversation_text,
    )


def build_enhanced_note(
    combined_note: str,
    visit_analysis: dict,
) -> str:
    """
    原文とVisit Analyzerの結果をEncounter Engineへ渡す。

    Visit Analyzerの結果だけに依存せず、
    必ず元の受付問診・診察会話も残す。
    """
    analysis_json = json.dumps(
        visit_analysis,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
{combined_note}

【Visit Analyzerによる診療構造】
{analysis_json}
""".strip()


def build_ai_outputs(
    combined_note: str,
    visit_analysis: dict,
    current_soap: str = "",
):
    """
    Visit Analyzerの結果を含めてEncounter JSONとSOAPを作成する。

    Encounter JSONは1回だけ生成し、
    Problem Listを同じEncounterへ統合する。
    """
    enhanced_note = build_enhanced_note(
        combined_note=combined_note,
        visit_analysis=visit_analysis,
    )

    encounter_service = EncounterService()

    encounter = encounter_service.create_encounter_json(
        enhanced_note
    )

    if not isinstance(encounter, dict):
        encounter = {}

    # Visit Analyzer結果を確実にEncounterへ保持する。
    encounter["visit_analysis"] = visit_analysis
    encounter["problems"] = visit_analysis.get(
        "problems",
        [],
    )

    encounter_json = json.dumps(
        encounter,
        ensure_ascii=False,
        indent=2,
    )

    if current_soap.strip():
        soap_service = IncrementalSOAPService()

        soap_result = soap_service.update_soap(
            current_soap=current_soap,
            combined_note=enhanced_note,
        )
    else:
        soap_service = SOAPService()

        # create_soap_from_encounter が実装済みなら、
        # Encounter JSONの重複生成を避ける。
        if hasattr(
            soap_service,
            "create_soap_from_encounter",
        ):
            soap_result = (
                soap_service.create_soap_from_encounter(
                    encounter
                )
            )
        else:
            soap_result = soap_service.create_soap(
                enhanced_note
            )

    quality_validator = ClinicalRecordValidator()

    quality_checks = quality_validator.validate(
        source_note=combined_note,
        encounter=encounter,
        soap_text=soap_result,
    )

    cds_service = CDSService()

    clinical_checks = (
        quality_checks
        + cds_service.get_checks(
            enhanced_note,
            encounter,
        )
    )

    reasoning = ClinicalReasoningEngine()

    diagnoses = reasoning.evaluate(
        enhanced_note,
        encounter,
    )

    return {
        "enhanced_note": enhanced_note,
        "encounter": encounter,
        "encounter_json": encounter_json,
        "soap_result": soap_result,
        "clinical_checks": clinical_checks,
        "diagnoses": diagnoses,
    }


def index(request):
    intake_note = ""
    encounter_note = ""
    soap_result = ""
    encounter_json = ""
    clinical_checks = []
    diagnoses = []
    referral_result = ""
    visit_analysis_json = ""

    if request.method == "POST":
        source = build_source_data_from_request(
            request
        )

        intake_note = source["intake_note"]
        encounter_note = source["encounter_note"]

        if source["combined_note"]:
            visit_analysis = analyze_visit(
                intake_note=source["intake_note"],
                conversation_text=source[
                    "conversation_text"
                ],
            )

            outputs = build_ai_outputs(
                combined_note=source["combined_note"],
                visit_analysis=visit_analysis,
            )

            encounter_json = outputs[
                "encounter_json"
            ]

            soap_result = outputs[
                "soap_result"
            ]

            clinical_checks = outputs[
                "clinical_checks"
            ]

            diagnoses = outputs[
                "diagnoses"
            ]

            visit_analysis_json = json.dumps(
                visit_analysis,
                ensure_ascii=False,
                indent=2,
            )

    return render(
        request,
        "soap/index.html",
        {
            "intake_note": intake_note,
            "medical_note": encounter_note,
            "soap_result": soap_result,
            "encounter_json": encounter_json,
            "clinical_checks": clinical_checks,
            "diagnoses": diagnoses,
            "referral_result": referral_result,
            "visit_analysis_json": (
                visit_analysis_json
            ),
        },
    )


@csrf_exempt
def transcribe_chunk(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "POSTのみ対応です"},
            status=405,
        )

    audio_file = request.FILES.get(
        "audio_file"
    )

    intake_note = request.POST.get(
        "intake_note",
        "",
    )

    is_final = (
        request.POST.get(
            "is_final",
            "false",
        ).lower()
        == "true"
    )

    if not audio_file:
        return JsonResponse(
            {"error": "音声ファイルがありません"},
            status=400,
        )

    try:
        speech_service = SpeechService()

        try:
            transcript = (
                speech_service.transcribe_audio(
                    audio_file=audio_file,
                    intake_note=intake_note,
                    is_final=is_final,
                )
            )
        except TypeError:
            # 旧SpeechServiceとの後方互換
            transcript = (
                speech_service.transcribe_audio(
                    audio_file
                )
            )

        return JsonResponse(
            {
                "transcript": transcript,
                "is_final": is_final,
            }
        )

    except Exception as exc:
        logger.exception("Audio transcription failed")
        return JsonResponse(
            {"error": str(exc)},
            status=500,
        )


@csrf_exempt
def generate_soap(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "POSTのみ対応です"},
            status=405,
        )

    source = build_source_data_from_request(
        request
    )

    current_soap = request.POST.get(
        "current_soap",
        "",
    )

    if not source["combined_note"]:
        return JsonResponse(
            {"error": "診察データがありません"},
            status=400,
        )

    try:
        visit_analysis = analyze_visit(
            intake_note=source["intake_note"],
            conversation_text=source[
                "conversation_text"
            ],
        )

        outputs = build_ai_outputs(
            combined_note=source["combined_note"],
            visit_analysis=visit_analysis,
            current_soap=current_soap,
        )

        return JsonResponse(
            {
                "visit_analysis": (
                    visit_analysis
                ),
                "encounter_json": outputs[
                    "encounter_json"
                ],
                "soap_result": outputs[
                    "soap_result"
                ],
                "clinical_checks": outputs[
                    "clinical_checks"
                ],
                "diagnoses": outputs[
                    "diagnoses"
                ],
            }
        )

    except Exception as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=500,
        )


@csrf_exempt
def generate_referral(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "POSTのみ対応です"},
            status=405,
        )

    source = build_source_data_from_request(
        request
    )

    if not source["combined_note"]:
        return JsonResponse(
            {"error": "診察データがありません"},
            status=400,
        )

    try:
        visit_analysis = analyze_visit(
            intake_note=source["intake_note"],
            conversation_text=source[
                "conversation_text"
            ],
        )

        enhanced_note = build_enhanced_note(
            combined_note=source["combined_note"],
            visit_analysis=visit_analysis,
        )

        encounter_service = EncounterService()

        encounter = (
            encounter_service.create_encounter_json(
                enhanced_note
            )
        )

        if not isinstance(encounter, dict):
            encounter = {}

        encounter["visit_analysis"] = (
            visit_analysis
        )

        encounter["problems"] = (
            visit_analysis.get(
                "problems",
                [],
            )
        )

        referral_service = ReferralService()

        referral_result = (
            referral_service.create_referral(
                enhanced_note,
                encounter,
            )
        )

        return JsonResponse(
            {
                "referral_result": (
                    referral_result
                )
            }
        )

    except Exception as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=500,
        )