import json
from django.shortcuts import render
from .services.soap_service import SOAPService
from .services.encounter_service import EncounterService
from .services.speech_service import SpeechService


def index(request):
    medical_note = ""
    transcript = ""
    soap_result = ""
    encounter_json = ""

    if request.method == "POST":
        medical_note = request.POST.get("medical_note", "")
        audio_file = request.FILES.get("audio_file")

        if audio_file:
            speech_service = SpeechService()
            transcript = speech_service.transcribe_audio(audio_file)
            medical_note = transcript

        if medical_note:
            encounter_service = EncounterService()
            encounter = encounter_service.create_encounter_json(medical_note)
            encounter_json = json.dumps(encounter, ensure_ascii=False, indent=2)

            soap_service = SOAPService()
            soap_result = soap_service.create_soap(medical_note)

    return render(request, "soap/index.html", {
        "medical_note": medical_note,
        "transcript": transcript,
        "encounter_json": encounter_json,
        "soap_result": soap_result,
    })