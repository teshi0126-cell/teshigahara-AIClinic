import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .services.soap_service import SOAPService
from .services.encounter_service import EncounterService
from .services.speech_service import SpeechService
from .services.cds_service import CDSService
from .services.reasoning.engine import ClinicalReasoningEngine
from .services.referral_service import ReferralService


def index(request):
    medical_note = ""
    soap_result = ""
    encounter_json = ""
    clinical_checks = []
    diagnoses = []
    referral_result = ""

    if request.method == "POST":
        medical_note = request.POST.get("medical_note", "")

        if medical_note:
            encounter_service = EncounterService()
            encounter = encounter_service.create_encounter_json(medical_note)
            encounter_json = json.dumps(encounter, ensure_ascii=False, indent=2)

            soap_service = SOAPService()
            soap_result = soap_service.create_soap(medical_note)

            cds_service = CDSService()
            clinical_checks = cds_service.get_checks(medical_note, encounter)

            reasoning = ClinicalReasoningEngine()
            diagnoses = reasoning.evaluate(medical_note, encounter)

    return render(request, "soap/index.html", {
        "medical_note": medical_note,
        "soap_result": soap_result,
        "encounter_json": encounter_json,
        "clinical_checks": clinical_checks,
        "diagnoses": diagnoses,
        "referral_result": referral_result,
    })


@csrf_exempt
def transcribe_chunk(request):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応です"}, status=405)

    audio_file = request.FILES.get("audio_file")

    if not audio_file:
        return JsonResponse({"error": "音声ファイルがありません"}, status=400)

    try:
        speech_service = SpeechService()
        transcript = speech_service.transcribe_audio(audio_file)
        return JsonResponse({"transcript": transcript})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def generate_soap(request):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応です"}, status=405)

    medical_note = request.POST.get("medical_note", "")

    if not medical_note:
        return JsonResponse({"error": "診察メモがありません"}, status=400)

    try:
        encounter_service = EncounterService()
        encounter = encounter_service.create_encounter_json(medical_note)
        encounter_json = json.dumps(encounter, ensure_ascii=False, indent=2)

        soap_service = SOAPService()
        soap_result = soap_service.create_soap(medical_note)

        cds_service = CDSService()
        clinical_checks = cds_service.get_checks(medical_note, encounter)

        reasoning = ClinicalReasoningEngine()
        diagnoses = reasoning.evaluate(medical_note, encounter)

        return JsonResponse({
            "encounter_json": encounter_json,
            "soap_result": soap_result,
            "clinical_checks": clinical_checks,
            "diagnoses": diagnoses,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def generate_referral(request):
    if request.method != "POST":
        return JsonResponse({"error": "POSTのみ対応です"}, status=405)

    medical_note = request.POST.get("medical_note", "")

    if not medical_note:
        return JsonResponse({"error": "診察メモがありません"}, status=400)

    try:
        encounter_service = EncounterService()
        encounter = encounter_service.create_encounter_json(medical_note)

        referral_service = ReferralService()
        referral_result = referral_service.create_referral(medical_note, encounter)

        return JsonResponse({
            "referral_result": referral_result,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)