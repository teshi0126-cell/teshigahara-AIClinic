let mediaRecorder;
let stream;
let isRecording = false;
let conversationChunks = [];

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusText = document.getElementById("status");

const intakeNote = document.getElementById("intakeNote");
const intakeNoteHidden = document.getElementById("intakeNoteHidden");
const medicalNote = document.getElementById("medicalNote");

const soapResult = document.getElementById("soap_result");
const referralResult = document.getElementById("referral_result");

const encounterJson = document.getElementById("encounter_json");

const clinicalChecks = document.getElementById("clinical_checks");
const diagnosisList = document.getElementById("diagnosis_list");

function syncIntakeBeforeSubmit() {
    intakeNoteHidden.value = intakeNote.value;
}

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

function scoreToStars(score) {
    if (score >= 80) return "★★★★★";
    if (score >= 70) return "★★★★☆";
    if (score >= 60) return "★★★☆☆";
    if (score >= 50) return "★★☆☆☆";
    return "★☆☆☆☆";
}

function renderDiagnoses(diagnoses) {
    diagnosisList.innerHTML = "";

    if (!diagnoses || diagnoses.length === 0) {
        diagnosisList.innerHTML = "<p>鑑別診断候補はありません。</p>";
        return;
    }

    diagnoses.forEach(dx => {
        const card = document.createElement("div");
        card.className = "diagnosis-card";

        const h3 = document.createElement("h3");
        h3.textContent = scoreToStars(dx.score) + " " + dx.name;

        const ul = document.createElement("ul");

        dx.reasons.forEach(r => {
            const li = document.createElement("li");
            li.textContent = r;
            ul.appendChild(li);
        });

        card.appendChild(h3);
        card.appendChild(ul);
        diagnosisList.appendChild(card);
    });
}

async function sendAudioChunk(blob) {
    if (!blob || blob.size < 2000) return;

    const formData = new FormData();
    formData.append("audio_file", blob, "chunk.webm");

    const response = await fetch("/transcribe_chunk/", {
        method: "POST",
        headers: {
            "X-CSRFToken": getCsrfToken()
        },
        body: formData
    });

    const data = await response.json();

    if (data.transcript) {
        const transcript = data.transcript.trim();

        if (transcript) {
            conversationChunks.push(transcript);
            medicalNote.value += transcript + "\n";
        }

        statusText.innerText = "SOAP更新中...";
        await updateSOAP();

        if (isRecording) {
            statusText.innerText = "録音中...";
        }
    }
}

async function updateSOAP() {
    const combinedExists = intakeNote.value.trim() || medicalNote.value.trim();

    if (!combinedExists) return;

    const formData = new FormData();
    formData.append("intake_note", intakeNote.value);
    formData.append("medical_note", medicalNote.value);
    formData.append("conversation_chunks", JSON.stringify(conversationChunks));

    const response = await fetch("/generate_soap/", {
        method: "POST",
        headers: {
            "X-CSRFToken": getCsrfToken()
        },
        body: formData
    });

    const data = await response.json();

    if (data.soap_result) {
        soapResult.value = data.soap_result;
    }

    if (data.encounter_json) {
        encounterJson.value = data.encounter_json;
    }

    if (data.clinical_checks) {
        clinicalChecks.innerHTML = "";

        data.clinical_checks.forEach(check => {
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

    if (data.diagnoses) {
        renderDiagnoses(data.diagnoses);
    }
}

async function generateReferral() {
    const combinedExists = intakeNote.value.trim() || medicalNote.value.trim();

    if (!combinedExists) {
        alert("受付問診または診察メモがありません。");
        return;
    }

    statusText.innerText = "紹介状作成中...";

    const formData = new FormData();
    formData.append("intake_note", intakeNote.value);
    formData.append("medical_note", medicalNote.value);
    formData.append("conversation_chunks", JSON.stringify(conversationChunks));

    const response = await fetch("/generate_referral/", {
        method: "POST",
        headers: {
            "X-CSRFToken": getCsrfToken()
        },
        body: formData
    });

    const data = await response.json();

    if (data.referral_result) {
        referralResult.value = data.referral_result;
        statusText.innerText = "紹介状を作成しました。";
    }

    if (data.error) {
        alert(data.error);
        statusText.innerText = "";
    }
}

function copySOAP() {
    soapResult.select();
    navigator.clipboard.writeText(soapResult.value);
    document.getElementById("copy_message").innerText = "SOAPをコピーしました。";
}

function copyReferral() {
    referralResult.select();
    navigator.clipboard.writeText(referralResult.value);
    document.getElementById("referral_copy_message").innerText = "紹介状をコピーしました。";
}

startBtn.onclick = async function() {
    conversationChunks = [];
    medicalNote.value = "";

    stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    isRecording = true;

    mediaRecorder = new MediaRecorder(stream, {
        mimeType: "audio/webm;codecs=opus"
    });

    mediaRecorder.ondataavailable = async function(event) {
        if (event.data && event.data.size > 0) {
            statusText.innerText = "文字起こし中...";
            await sendAudioChunk(event.data);

            if (isRecording) {
                statusText.innerText = "録音中...";
            }
        }
    };

    mediaRecorder.onstop = function() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }

        isRecording = false;
        startBtn.disabled = false;
        stopBtn.disabled = true;
        statusText.innerText = "録音停止";
    };

    mediaRecorder.start(10000);

    startBtn.disabled = true;
    stopBtn.disabled = false;
    statusText.innerText = "録音中...";
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