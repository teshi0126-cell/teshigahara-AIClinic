from django.shortcuts import render
from .services.soap_service import SOAPService


def index(request):
    medical_note = ""
    soap_result = ""

    if request.method == "POST":
        medical_note = request.POST.get("medical_note", "")

        if medical_note:
            service = SOAPService()
            soap_result = service.create_soap(medical_note)

    return render(request, "soap/index.html", {
        "medical_note": medical_note,
        "soap_result": soap_result,
    })