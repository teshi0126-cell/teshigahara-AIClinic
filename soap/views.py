import json
from django.shortcuts import render
from .services.soap_service import SOAPService
from .services.encounter_service import EncounterService


def index(request):
    medical_note = ""
    soap_result = ""
    encounter_json = ""

    if request.method == "POST":
        medical_note = request.POST.get("medical_note", "")

        if medical_note:
            encounter_service = EncounterService()
            encounter = encounter_service.create_encounter_json(medical_note)
            encounter_json = json.dumps(
                encounter,
                ensure_ascii=False,
                indent=2
            )

            soap_service = SOAPService()
            soap_result = soap_service.create_soap(medical_note)

    return render(request, "soap/index.html", {
        "medical_note": medical_note,
        "soap_result": soap_result,
        "encounter_json": encounter_json,
    })