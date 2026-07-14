let mediaRecorder;
let stream;
let isRecording = false;
let sessionState = "idle";
let sessionDirty = false;
let allowPageUnload = false;
let retainedFinalBlob = null;
let retainedFinalTranscript = "";

let realtimeChunks = [];
let fullAudioChunks = [];
let conversationChunks = [];
let activeTranscriptions = new Set();
let pendingTranscripts = new Map();
let nextChunkSequence = 0;
let nextChunkToRender = 0;

let audioContext;
let audioSource;
let audioProcessor;
let inputGain;
let voiceCompressor;
let recordingDestination;
let analyserNode;
let audioLevelFrame;
let pcmBuffers = [];
let pcmSampleCount = 0;

const REALTIME_CHUNK_SECONDS = 10;
const MICROPHONE_GAIN = 2.5;

const newSessionBtn = document.getElementById("newSessionBtn");
const startBtn = document.getElementById("startBtn");
const recordingConsent = document.getElementById("recordingConsent");
const stopBtn = document.getElementById("stopBtn");
const retryFinalBtn = document.getElementById("retryFinalBtn");
const completeSessionBtn = document.getElementById("completeSessionBtn");
const sessionHint = document.getElementById("sessionHint");
const soapForm = document.getElementById("soapForm");
const statusText = document.getElementById("status");
const soapStatus = document.getElementById("soapStatus");

const intakeNote = document.getElementById("intakeNote");
const intakeNoteHidden = document.getElementById("intakeNoteHidden");
const medicalNote = document.getElementById("medicalNote");

const soapResult = document.getElementById("soap_result");
const referralResult = document.getElementById("referral_result");
const encounterJson = document.getElementById("encounter_json");

const clinicalChecks = document.getElementById("clinical_checks");
const diagnosisList = document.getElementById("diagnosis_list");
const microphoneDevice = document.getElementById("microphoneDevice");
const audioLevelMeter = document.getElementById("audioLevelMeter");
const audioLevelText = document.getElementById("audioLevelText");

function syncIntakeBeforeSubmit() {
    intakeNoteHidden.value = intakeNote.value;
}

function setSoapStatus(text) {
    if (soapStatus) {
        soapStatus.innerText = text;
    }
}

function isSessionBusy() {
    return [
        "recording",
        "stopping",
        "finalizing"
    ].includes(sessionState);
}

function setSessionState(state, hint = "") {
    sessionState = state;

    startBtn.disabled = state !== "idle";

    if (state === "idle") {
        startBtn.disabled = !recordingConsent.checked;
    }

    stopBtn.disabled = state !== "recording";
    newSessionBtn.disabled = isSessionBusy();

    retryFinalBtn.hidden = !(
        state === "error"
        && (retainedFinalBlob || retainedFinalTranscript)
    );

    completeSessionBtn.disabled = !(
        state === "ready"
        && sessionDirty
    );

    sessionHint.className = "session-hint";

    if (state === "error") {
        sessionHint.classList.add("error");
    } else if (state === "ready" && !sessionDirty) {
        sessionHint.classList.add("complete");
    }

    if (hint) {
        sessionHint.innerText = hint;
    }
}

function markSessionDirty() {
    sessionDirty = true;

    if (sessionState === "ready") {
        completeSessionBtn.disabled = false;
    }
}

function resetRecordingBuffers() {
    realtimeChunks = [];
    fullAudioChunks = [];
    conversationChunks = [];
    activeTranscriptions = new Set();
    pendingTranscripts = new Map();
    nextChunkSequence = 0;
    nextChunkToRender = 0;
    pcmBuffers = [];
    pcmSampleCount = 0;
    retainedFinalBlob = null;
    retainedFinalTranscript = "";
}

function clearSessionOutputs() {
    intakeNote.value = "";
    intakeNoteHidden.value = "";
    medicalNote.value = "";
    soapResult.value = "";
    encounterJson.value = "";
    referralResult.value = "";
    clinicalChecks.innerHTML = "";
    diagnosisList.innerHTML = "";
    recordingConsent.checked = false;

    const copyMessage = document.getElementById(
        "copy_message"
    );
    const referralCopyMessage = document.getElementById(
        "referral_copy_message"
    );

    if (copyMessage) copyMessage.innerText = "";
    if (referralCopyMessage) {
        referralCopyMessage.innerText = "";
    }
}

function startNewSession() {
    if (isSessionBusy()) return;

    if (
        sessionDirty
        && !window.confirm(
            "現在の診察内容はまだDigiKar転記済みに"
            + "なっていません。内容を消して新しい診察を"
            + "開始しますか？"
        )
    ) {
        return;
    }

    resetRecordingBuffers();
    clearSessionOutputs();
    sessionDirty = false;

    statusText.innerText = "待機中";
    setSoapStatus("待機中");
    setSessionState(
        "idle",
        "受付問診を入力して診察を開始できます。"
    );
}

function getCsrfToken() {
    const formToken = document.querySelector(
        "[name=csrfmiddlewaretoken]"
    );

    if (formToken && formToken.value) {
        return formToken.value;
    }

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

async function transcribeBlob(blob, filename, isFinal = false) {
    if (!blob || blob.size < 500) return "";

    const formData = new FormData();
    formData.append("audio_file", blob, filename);
    formData.append("intake_note", intakeNote.value);
    formData.append("is_final", isFinal ? "true" : "false");

    let response;
    let data;

    try {
        response = await fetch("/transcribe_chunk/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken()
            },
            body: formData
        });

        data = await response.json();
    } catch (error) {
        console.error("文字起こし通信エラー", error);
        statusText.innerText = "文字起こし通信エラー";
        setSoapStatus("再試行待ち");
        return "";
    }

    if (!response.ok || data.error) {
        console.error("文字起こしエラー", data.error);
        statusText.innerText = (
            "文字起こしエラー："
            + (data.error || response.status)
        );
        setSoapStatus("再試行待ち");
        return "";
    }

    return (data.transcript || "").trim();
}

async function updateSOAP() {
    const combinedExists = intakeNote.value.trim() || medicalNote.value.trim();

    if (!combinedExists) return false;

    const formData = new FormData();
    formData.append("intake_note", intakeNote.value);
    formData.append("medical_note", medicalNote.value);
    formData.append("conversation_chunks", JSON.stringify(conversationChunks));
    formData.append("current_soap", soapResult.value);

    let response;
    let data;

    try {
        response = await fetch("/generate_soap/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken()
            },
            body: formData
        });

        data = await response.json();
    } catch (error) {
        console.error("SOAP生成通信エラー", error);
        statusText.innerText = "SOAP生成通信エラー";
        setSoapStatus("再試行待ち");
        return false;
    }

    if (data.soap_result) {
        soapResult.value = data.soap_result;
        setSoapStatus("更新済み");
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

    if (!response.ok || data.error) {
        statusText.innerText = (
            "エラー："
            + (data.error || response.status)
        );
        setSoapStatus("再試行待ち");
        return false;
    }

    return Boolean(data.soap_result);
}

function updateAudioLevel() {
    if (!analyserNode || !isRecording) return;

    const samples = new Float32Array(
        analyserNode.fftSize
    );
    analyserNode.getFloatTimeDomainData(samples);

    let sumSquares = 0;

    for (const sample of samples) {
        sumSquares += sample * sample;
    }

    const rms = Math.sqrt(sumSquares / samples.length);
    const decibels = rms > 0
        ? 20 * Math.log10(rms)
        : -60;
    const clampedDb = Math.max(-60, Math.min(0, decibels));
    const percentage = ((clampedDb + 60) / 60) * 100;

    audioLevelMeter.value = percentage;

    if (clampedDb < -42) {
        audioLevelText.innerText = "小さい";
    } else if (clampedDb > -8) {
        audioLevelText.innerText = "大きすぎ";
    } else {
        audioLevelText.innerText = "適正";
    }

    audioLevelFrame = requestAnimationFrame(
        updateAudioLevel
    );
}

function startAudioLevelMonitor(mediaStream) {
    const audioTrack = mediaStream.getAudioTracks()[0];

    microphoneDevice.innerText = audioTrack
        ? audioTrack.label || "選択中のマイク"
        : "マイクを確認できません";

    updateAudioLevel();
}

function stopAudioLevelMonitor() {
    if (audioLevelFrame) {
        cancelAnimationFrame(audioLevelFrame);
    }

    audioLevelFrame = null;
    audioLevelMeter.value = 0;
    audioLevelText.innerText = "停止";
}

function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    function writeText(offset, text) {
        for (let i = 0; i < text.length; i += 1) {
            view.setUint8(offset + i, text.charCodeAt(i));
        }
    }

    writeText(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeText(36, "data");
    view.setUint32(40, samples.length * 2, true);

    let offset = 44;

    for (const sample of samples) {
        const clamped = Math.max(-1, Math.min(1, sample));
        const value = clamped < 0
            ? clamped * 0x8000
            : clamped * 0x7fff;

        view.setInt16(offset, value, true);
        offset += 2;
    }

    return new Blob([buffer], { type: "audio/wav" });
}

function mergePcmBuffers(buffers, totalLength) {
    const merged = new Float32Array(totalLength);
    let offset = 0;

    for (const buffer of buffers) {
        merged.set(buffer, offset);
        offset += buffer.length;
    }

    return merged;
}

function queueRealtimePcmChunk(force = false) {
    if (!audioContext || pcmSampleCount === 0) return;

    const minimumSamples = force
        ? Math.floor(audioContext.sampleRate)
        : Math.floor(
            audioContext.sampleRate * REALTIME_CHUNK_SECONDS
        );

    if (pcmSampleCount < minimumSamples) return;

    const samples = mergePcmBuffers(
        pcmBuffers,
        pcmSampleCount
    );

    pcmBuffers = [];
    pcmSampleCount = 0;

    const wavBlob = encodeWav(
        samples,
        audioContext.sampleRate
    );
    const sequence = nextChunkSequence;
    nextChunkSequence += 1;

    statusText.innerText = "文字起こし中...";

    const task = handleRealtimeChunk(
        wavBlob,
        sequence
    );

    activeTranscriptions.add(task);

    task.finally(() => {
        activeTranscriptions.delete(task);
    });
}

function startRealtimePcmCapture(mediaStream) {
    audioContext = new AudioContext();
    audioSource = audioContext.createMediaStreamSource(
        mediaStream
    );
    inputGain = audioContext.createGain();
    inputGain.gain.value = MICROPHONE_GAIN;

    voiceCompressor = (
        audioContext.createDynamicsCompressor()
    );
    voiceCompressor.threshold.value = -24;
    voiceCompressor.knee.value = 20;
    voiceCompressor.ratio.value = 6;
    voiceCompressor.attack.value = 0.003;
    voiceCompressor.release.value = 0.25;

    recordingDestination = (
        audioContext.createMediaStreamDestination()
    );

    audioProcessor = audioContext.createScriptProcessor(
        4096,
        1,
        1
    );

    audioProcessor.onaudioprocess = event => {
        if (!isRecording) return;

        const samples = new Float32Array(
            event.inputBuffer.getChannelData(0)
        );

        pcmBuffers.push(samples);
        pcmSampleCount += samples.length;

        queueRealtimePcmChunk(false);
    };

    audioSource.connect(inputGain);
    inputGain.connect(voiceCompressor);

    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 2048;
    analyserNode.smoothingTimeConstant = 0.75;

    voiceCompressor.connect(analyserNode);
    analyserNode.connect(audioProcessor);
    analyserNode.connect(recordingDestination);
    audioProcessor.connect(audioContext.destination);
    startAudioLevelMonitor(mediaStream);

    return recordingDestination.stream;
}

async function stopRealtimePcmCapture() {
    queueRealtimePcmChunk(true);
    stopAudioLevelMonitor();

    if (audioProcessor) {
        audioProcessor.disconnect();
        audioProcessor.onaudioprocess = null;
    }

    if (analyserNode) {
        analyserNode.disconnect();
    }

    if (voiceCompressor) {
        voiceCompressor.disconnect();
    }

    if (inputGain) {
        inputGain.disconnect();
    }

    if (audioSource) {
        audioSource.disconnect();
    }

    if (recordingDestination) {
        recordingDestination.stream
            .getTracks()
            .forEach(track => track.stop());
    }

    if (audioContext) {
        await audioContext.close();
    }

    audioProcessor = null;
    analyserNode = null;
    voiceCompressor = null;
    inputGain = null;
    recordingDestination = null;
    audioSource = null;
    audioContext = null;
}

function flushRealtimeTranscripts() {
    while (pendingTranscripts.has(nextChunkToRender)) {
        const transcript = pendingTranscripts.get(nextChunkToRender);
        pendingTranscripts.delete(nextChunkToRender);
        nextChunkToRender += 1;

        if (transcript) {
            conversationChunks.push(transcript);
            medicalNote.value += transcript + "\n";
        }
    }
}

async function handleRealtimeChunk(blob, sequence) {
    try {
        const transcript = await transcribeBlob(
            blob,
            "chunk_" + sequence + ".wav",
            false
        );

        pendingTranscripts.set(sequence, transcript);
        flushRealtimeTranscripts();
        setSoapStatus("診察終了後に生成");
    } catch (error) {
        console.error(error);
        pendingTranscripts.set(sequence, "");
        flushRealtimeTranscripts();
    }

    if (isRecording) {
        statusText.innerText = "録音中...";
    }
}

async function finalizeFullRecording(blobOverride = null) {
    if (!blobOverride && fullAudioChunks.length === 0) {
        return;
    }

    setSessionState(
        "finalizing",
        "最終文字起こしとSOAPを生成しています。"
    );
    statusText.innerText = "最終文字起こし中...";
    setSoapStatus("最終文字起こし中");

    retainedFinalBlob = blobOverride || new Blob(
        fullAudioChunks,
        {
            type: "audio/webm;codecs=opus"
        }
    );

    await stopRealtimePcmCapture();
    await Promise.all(Array.from(activeTranscriptions));

    const finalTranscript = await transcribeBlob(
        retainedFinalBlob,
        "full_recording.webm",
        true
    );

    if (!finalTranscript) {
        markSessionDirty();
        statusText.innerText = (
            "最終文字起こしに失敗。"
            + "途中の文字起こしと音声を保持しています。"
        );
        setSoapStatus("再試行待ち");
        setSessionState(
            "error",
            "最終処理を再試行できます。"
            + "画面を閉じないでください。"
        );
        return;
    }

    retainedFinalTranscript = finalTranscript;
    medicalNote.value = finalTranscript + "\n";
    conversationChunks = [finalTranscript];
    markSessionDirty();

    statusText.innerText = "最終SOAP更新中...";
    setSoapStatus("最終更新中");

    const soapUpdated = await updateSOAP();

    if (!soapUpdated) {
        statusText.innerText = (
            "文字起こしは保存済み。SOAP生成を再試行できます。"
        );
        setSoapStatus("再試行待ち");
        setSessionState(
            "error",
            "最終文字起こしを保持しています。"
            + "SOAP生成を再試行してください。"
        );
        return;
    }

    retainedFinalBlob = null;
    retainedFinalTranscript = "";
    statusText.innerText = "録音停止・SOAP更新済み";
    setSoapStatus("更新済み");
    setSessionState(
        "ready",
        "SOAPをDigiKarへ転記後、"
        + "「DigiKar転記済み」を押してください。"
    );
}

async function retryFinalProcessing() {
    if (
        sessionState !== "error"
        || (!retainedFinalBlob && !retainedFinalTranscript)
    ) {
        return;
    }

    if (retainedFinalTranscript) {
        setSessionState(
            "finalizing",
            "保持中の文字起こしからSOAPを再生成しています。"
        );
        medicalNote.value = retainedFinalTranscript + "\n";
        conversationChunks = [retainedFinalTranscript];

        const soapUpdated = await updateSOAP();

        if (soapUpdated) {
            retainedFinalBlob = null;
            retainedFinalTranscript = "";
            statusText.innerText = "SOAP更新済み";
            setSoapStatus("更新済み");
            setSessionState(
                "ready",
                "SOAPをDigiKarへ転記後、"
                + "「DigiKar転記済み」を押してください。"
            );
        } else {
            setSessionState(
                "error",
                "SOAP生成に失敗しました。再試行できます。"
            );
        }

        return;
    }

    await finalizeFullRecording(retainedFinalBlob);
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

newSessionBtn.onclick = startNewSession;
retryFinalBtn.onclick = retryFinalProcessing;

completeSessionBtn.onclick = function() {
    if (sessionState !== "ready") return;

    sessionDirty = false;
    statusText.innerText = "DigiKar転記済み";
    setSessionState(
        "ready",
        "転記済みです。「新しい診察」へ進めます。"
    );
};

startBtn.onclick = async function() {
    if (
        sessionState !== "idle"
        || !recordingConsent.checked
    ) {
        setSessionState(
            "idle",
            "患者さんへの録音・AI処理の説明確認が必要です。"
        );
        return;
    }

    resetRecordingBuffers();

    medicalNote.value = "";
    soapResult.value = "";
    encounterJson.value = "";
    referralResult.value = "";
    clinicalChecks.innerHTML = "";
    diagnosisList.innerHTML = "";

    setSoapStatus("診察終了後に生成");
    setSessionState(
        "finalizing",
        "マイクを準備しています。"
    );

    try {
        stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
                channelCount: 1
            }
        });
    } catch (error) {
        console.error("マイク取得エラー", error);
        statusText.innerText = "マイクを使用できません";
        setSoapStatus("待機中");
        setSessionState(
            "idle",
            "マイクの接続とブラウザの許可を確認してください。"
        );
        return;
    }

    isRecording = true;
    markSessionDirty();

    const amplifiedStream = startRealtimePcmCapture(
        stream
    );

    mediaRecorder = new MediaRecorder(amplifiedStream, {
        mimeType: "audio/webm;codecs=opus"
    });

    mediaRecorder.ondataavailable = function(event) {
        if (event.data && event.data.size > 0) {
            fullAudioChunks.push(event.data);
        }
    };

    mediaRecorder.onstop = async function() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }

        isRecording = false;
        await finalizeFullRecording();
    };

    mediaRecorder.start(5000);

    statusText.innerText = "録音中...";
    setSessionState(
        "recording",
        "録音中です。患者切替や画面終了はできません。"
    );
};

stopBtn.onclick = function() {
    if (
        sessionState !== "recording"
        || !mediaRecorder
        || mediaRecorder.state !== "recording"
    ) {
        return;
    }

    isRecording = false;
    setSessionState(
        "stopping",
        "録音を停止しています。連続して押さないでください。"
    );
    mediaRecorder.requestData();

    setTimeout(() => {
        if (mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        }
    }, 1200);
};

[intakeNote, medicalNote, soapResult].forEach(element => {
    element.addEventListener("input", markSessionDirty);
});

recordingConsent.addEventListener("change", function() {
    if (sessionState !== "idle") return;

    setSessionState(
        "idle",
        recordingConsent.checked
            ? "診察を開始できます。"
            : "録音・AI処理の説明確認が必要です。"
    );
});

soapForm.addEventListener("submit", function() {
    syncIntakeBeforeSubmit();
    allowPageUnload = true;
});

window.addEventListener("beforeunload", function(event) {
    if (
        allowPageUnload
        || (!sessionDirty && !isSessionBusy())
    ) {
        return;
    }

    event.preventDefault();
    event.returnValue = "";
});

if (soapResult.value.trim()) {
    sessionDirty = true;
    setSessionState(
        "ready",
        "SOAPをDigiKarへ転記後、"
        + "「DigiKar転記済み」を押してください。"
    );
} else {
    sessionDirty = Boolean(
        intakeNote.value.trim()
        || medicalNote.value.trim()
    );
    setSessionState(
        "idle",
        "受付問診を入力して診察を開始できます。"
    );
}
