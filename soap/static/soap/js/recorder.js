let mediaRecorder;
let stream;
let isRecording = false;

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusText = document.getElementById("status");
const medicalNote = document.getElementById("medicalNote");
const soapResult = document.getElementById("soap_result");
const encounterJson = document.getElementById("encounter_json");
const clinicalChecks = document.getElementById("clinical_checks");

function getCsrfToken() {
    const name = "csrftoken";
    const cookies = document.cookie.split(";");
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + "=")) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return "";
}

async function sendAudioChunk(blob) {
    if (!blob || blob.size < 2000) return;

    const formData = new FormData();
    formData.append("audio_file", blob, "chunk.webm");

    const response = await fetch("/transcribe_chunk/", {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        body: formData
    });

    const data = await response.json();

    if (data.transcript) {
        medicalNote.value += data.transcript + "\n";
        statusText.innerText = "SOAP更新中...";
        await updateSOAP();
        if (isRecording) statusText.innerText = "録音中...";
    }
}

async function updateSOAP() {
    if (!medicalNote.value.trim()) return;

    const formData = new FormData();
    formData.append("medical_note", medicalNote.value);

    const response = await fetch("/generate_soap/", {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        body: formData
    });

    const data = await response.json();

    if (data.soap_result) soapResult.value = data.soap_result;
    if (data.encounter_json) encounterJson.value = data.encounter_json;

    if (data.clinical_checks) {
        clinicalChecks.innerHTML = "";

        data.clinical_checks.forEach(function(check) {
            const wrapper = document.createElement("div");
            wrapper.className = "check-item " + check.level;

            const category = document.createElement("span");
            category.className = "check-category";
            category.textContent = "[" + check.category + "] ";

            const label = document.createElement("label");
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = check.checked;

            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(" " + check.item));

            wrapper.appendChild(category);
            wrapper.appendChild(label);

            clinicalChecks.appendChild(wrapper);
         });
    }
}

startBtn.onclick = async function() {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    isRecording = true;
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });

    mediaRecorder.ondataavailable = async function(event) {
        if (event.data && event.data.size > 0) {
            statusText.innerText = "文字起こし中...";
            await sendAudioChunk(event.data);
            if (isRecording) statusText.innerText = "録音中...";
        }
    };

    mediaRecorder.onstop = function() {
        if (stream) stream.getTracks().forEach(track => track.stop());

        isRecording = false;
        startBtn.disabled = false;
        stopBtn.disabled = true;
        statusText.innerText = "録音停止。必要に応じてSOAPを確認してください。";
        statusText.className = "";
    };

    mediaRecorder.start(10000);

    startBtn.disabled = true;
    stopBtn.disabled = false;
    statusText.innerText = "録音中...";
    statusText.className = "recording";
};

stopBtn.onclick = function() {
    isRecording = false;

    if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.requestData();
        setTimeout(() => {
            if (mediaRecorder.state === "recording") {
                mediaRecorder.stop();
            }
        }, 300);
    }
};

function copySOAP() {
    soapResult.select();
    navigator.clipboard.writeText(soapResult.value);
    document.getElementById("copy_message").innerText = "SOAPをコピーしました。";
}