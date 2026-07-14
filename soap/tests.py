import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .services.soap_service import SOAPService
from .services.speech_service import SpeechService
from .services.visit_analyzer_service import VisitAnalyzerService


class VisitAnalyzerValidationTests(SimpleTestCase):
    def setUp(self):
        self.service = VisitAnalyzerService.__new__(
            VisitAnalyzerService
        )

    def test_invalid_values_are_normalized(self):
        result = self.service.validate_result(
            {
                "visit_type": [
                    "test_result_review",
                    "unknown",
                    "test_result_review",
                ],
                "visit_summary": " 検査結果を説明 ",
                "problems": [
                    {
                        "title": " CK上昇 ",
                        "status": "invalid",
                        "relevance": "invalid",
                        "include_in_soap": "false",
                        "objective": ["CK高値", "CK高値", ""],
                    },
                    {"title": ""},
                    "invalid",
                ],
                "discarded_conversation": ["お疲れ様です"],
            }
        )

        self.assertEqual(
            result["visit_type"],
            ["test_result_review"],
        )
        self.assertEqual(
            result["visit_summary"],
            "検査結果を説明",
        )
        self.assertEqual(len(result["problems"]), 1)
        problem = result["problems"][0]
        self.assertEqual(problem["title"], "CK上昇")
        self.assertEqual(problem["status"], "unclear")
        self.assertEqual(problem["relevance"], "active")
        self.assertFalse(problem["include_in_soap"])
        self.assertEqual(problem["objective"], ["CK高値"])

    def test_empty_input_does_not_call_ai(self):
        service = VisitAnalyzerService.__new__(
            VisitAnalyzerService
        )
        service.ai = Mock()

        result = service.analyze("", "  ")

        self.assertEqual(result, service.empty_result())
        service.ai.generate_text.assert_not_called()


class SOAPServiceTests(SimpleTestCase):
    def test_existing_encounter_is_used_without_regeneration(self):
        service = SOAPService.__new__(SOAPService)
        service.ai = Mock()
        service.ai.generate_text.return_value = "S: 経過良好"
        service.encounter_service = Mock()

        encounter = {
            "assessment": ["脂質は正常範囲"],
            "plan": ["内服継続"],
        }

        result = service.create_soap_from_encounter(encounter)

        self.assertEqual(result, "S: 経過良好")
        service.encounter_service.create_encounter_json.assert_not_called()

        prompt = service.ai.generate_text.call_args.args[0]
        self.assertIn(
            json.dumps(
                encounter,
                ensure_ascii=False,
                indent=2,
            ),
            prompt,
        )


class SpeechServiceTests(SimpleTestCase):
    @patch("soap.services.speech_service.client")
    def test_intake_prompt_is_kept_for_final_transcription(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.return_value = (
            SimpleNamespace(text="ディジカル")
        )

        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            "脂質異常症、CK"
        )
        service.medical_dictionary.correct.return_value = "DigiKar"

        audio = SimpleUploadedFile(
            "test.webm",
            b"audio",
            content_type="audio/webm",
        )

        result = service.transcribe_audio(
            audio_file=audio,
            intake_note="検査結果",
            is_final=False,
        )

        self.assertEqual(result, "DigiKar")
        kwargs = (
            mock_client.audio.transcriptions.create.call_args.kwargs
        )
        self.assertEqual(kwargs["prompt"], "脂質異常症、CK")
        service.medical_dictionary.build_transcription_prompt.assert_called_once_with(
            "検査結果"
        )


    @patch("soap.services.speech_service.client")
    def test_final_transcription_uses_dual_pass_and_reconciliation(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.side_effect = [
            SimpleNamespace(
                text=(
                    "今日はどうされましたか。"
                    "頭が痛いです。"
                )
            ),
            SimpleNamespace(
                segments=[
                    SimpleNamespace(
                        speaker="speaker_0",
                        text="今日はどうされましたか。",
                    ),
                    SimpleNamespace(
                        speaker="speaker_1",
                        text="頭が痛いです。",
                    ),
                ]
            ),
        ]
        mock_client.responses.create.return_value = (
            SimpleNamespace(
                output_text=(
                    "話者A：今日はどうされましたか。\n"
                    "話者B：頭が痛いです。"
                )
            )
        )

        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            "頭痛、咽頭痛"
        )
        service.medical_dictionary.correct.side_effect = (
            lambda text: text
        )

        audio = SimpleUploadedFile(
            "final.webm",
            b"audio",
            content_type="audio/webm",
        )

        result = service.transcribe_audio(
            audio_file=audio,
            intake_note="頭痛",
            is_final=True,
        )

        calls = (
            mock_client.audio.transcriptions.create.call_args_list
        )
        self.assertEqual(len(calls), 2)

        accurate_kwargs = calls[0].kwargs
        self.assertEqual(
            accurate_kwargs["model"],
            "gpt-4o-transcribe",
        )
        self.assertEqual(
            accurate_kwargs["prompt"],
            "頭痛、咽頭痛",
        )

        diarized_kwargs = calls[1].kwargs
        self.assertEqual(
            diarized_kwargs["model"],
            "gpt-4o-transcribe-diarize",
        )
        self.assertEqual(
            diarized_kwargs["response_format"],
            "diarized_json",
        )
        self.assertEqual(
            diarized_kwargs["chunking_strategy"],
            "auto",
        )
        self.assertNotIn("prompt", diarized_kwargs)

        merge_prompt = (
            mock_client.responses.create.call_args.kwargs[
                "input"
            ]
        )
        self.assertIn(
            "今日はどうされましたか。頭が痛いです。",
            merge_prompt,
        )
        self.assertIn(
            "話者A：今日はどうされましたか。",
            merge_prompt,
        )
        self.assertIn(
            "どちらにも存在しない症状",
            merge_prompt,
        )
        self.assertEqual(
            result,
            "話者A：今日はどうされましたか。\n"
            "話者B：頭が痛いです。",
        )

    @patch("soap.services.speech_service.client")
    def test_final_transcription_falls_back_when_diarization_fails(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.side_effect = [
            SimpleNamespace(
                text="咽頭痛があります。"
            ),
            RuntimeError("diarization unavailable"),
        ]

        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            "咽頭痛"
        )
        service.medical_dictionary.correct.side_effect = (
            lambda text: text
        )

        audio = SimpleUploadedFile(
            "final.webm",
            b"audio",
            content_type="audio/webm",
        )

        with self.assertLogs(
            "soap.services.speech_service",
            level="ERROR",
        ) as captured_logs:
            result = service.transcribe_audio(
                audio_file=audio,
                intake_note="のどが痛い",
                is_final=True,
            )

        self.assertEqual(
            result,
            "咽頭痛があります。",
        )
        self.assertTrue(
            any(
                "Speaker diarization failed"
                in message
                for message in captured_logs.output
            )
        )
        mock_client.responses.create.assert_not_called()

    @patch("soap.services.speech_service.client")
    def test_invalid_reconciliation_falls_back_to_accurate_text(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.side_effect = [
            SimpleNamespace(
                text="咳があります。"
            ),
            SimpleNamespace(
                segments=[
                    {
                        "speaker": "speaker_0",
                        "text": "咳があります。",
                    }
                ]
            ),
        ]
        mock_client.responses.create.return_value = (
            SimpleNamespace(
                output_text="診察内容を要約しました。"
            )
        )

        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            "咳"
        )
        service.medical_dictionary.correct.side_effect = (
            lambda text: text
        )

        audio = SimpleUploadedFile(
            "final.webm",
            b"audio",
            content_type="audio/webm",
        )

        result = service.transcribe_audio(
            audio_file=audio,
            intake_note="咳",
            is_final=True,
        )

        self.assertEqual(result, "咳があります。")

    def test_merged_transcript_accepts_only_speaker_lines(self):
        valid = (
            "```text\n"
            "話者A：こんにちは。\n"
            "話者B：はい。\n"
            "```"
        )

        result = SpeechService.clean_merged_transcript(
            valid
        )

        self.assertEqual(
            result,
            "話者A：こんにちは。\n話者B：はい。",
        )
        self.assertEqual(
            SpeechService.clean_merged_transcript(
                "SOAP：咽頭炎"
            ),
            "",
        )


class SOAPConfirmationGuardTests(SimpleTestCase):
    def test_confirmation_section_is_removed_when_missing_items_empty(self):
        soap = (
            "S：\n- 検査結果確認\n\n"
            "O：\n- CK軽度高値\n\n"
            "確認すべき点：\n- 褐色尿の有無"
        )

        result = SOAPService.remove_unsupported_confirmation_section(
            soap,
            {"missing_items": []},
        )

        self.assertNotIn("確認すべき点", result)
        self.assertNotIn("褐色尿", result)
        self.assertIn("CK軽度高値", result)

    def test_confirmation_section_is_removed_when_missing_items_exist(self):
        soap = "P：\n- 経過観察\n\n確認すべき点：\n- CK値"

        result = SOAPService.remove_unsupported_confirmation_section(
            soap,
            {"missing_items": ["CK値"]},
        )

        self.assertEqual(result, "P：\n- 経過観察")


class SOAPPlanGuardTests(SimpleTestCase):
    def test_plan_action_without_encounter_evidence_is_removed(self):
        soap = (
            "P：\n"
            "- 薬を継続する。\n"
            "- CK高値について経過観察。"
        )
        encounter = {
            "plan": ["薬を継続する"],
            "assessment": ["CKが少し高い"],
        }

        result = SOAPService.remove_unsupported_plan_actions(
            soap,
            encounter,
        )

        self.assertIn("薬を継続する", result)
        self.assertNotIn("経過観察", result)

    def test_plan_action_with_encounter_evidence_is_kept(self):
        soap = "P：\n- 1か月後に再診。"
        encounter = {"plan": ["1か月後に再診"]}

        result = SOAPService.remove_unsupported_plan_actions(
            soap,
            encounter,
        )

        self.assertEqual(result, soap)


class SOAPOutputCleanupTests(SimpleTestCase):
    def test_inferred_exam_action_is_removed_from_plan(self):
        soap = (
            "S：\n- 体調は変わらない。\n\n"
            "P：\n- 注射治療を継続する。\n"
            "- 聴診を行う。"
        )
        encounter = {
            "encounter": {
                "raw_text": (
                    "注射を続けていきましょう。"
                    "ちょっと音を聞かせて。"
                )
            },
            "plan": [
                "注射治療を継続する",
                "聴診を行う",
            ],
        }

        result = SOAPService.remove_inferred_exam_actions(
            soap,
            encounter,
        )

        self.assertIn("注射治療を継続", result)
        self.assertNotIn("聴診を行う", result)

    def test_explicit_exam_plan_is_kept(self):
        soap = "P：\n- 次回も聴診を行う。"
        encounter = {
            "encounter": {
                "raw_text": "次回も聴診を行います。"
            },
            "plan": ["次回も聴診を行う"],
        }

        result = SOAPService.remove_inferred_exam_actions(
            soap,
            encounter,
        )

        self.assertEqual(result, soap)

    def test_empty_bullets_are_removed(self):
        soap = (
            "S：\n- 体調は変わらない。\n\n"
            "O：\n-\n\n"
            "A：\n- 内服継続可能。"
        )

        result = SOAPService.remove_empty_bullets(
            soap
        )

        self.assertIn("O：", result)
        self.assertNotIn("O：\n-", result)
        self.assertIn("内服継続可能", result)

    def test_exact_duplicate_bullets_are_removed(self):
        soap = (
            "P：\n"
            "- 注射治療を継続する。\n"
            "- 注射治療を継続する"
        )

        result = SOAPService.remove_duplicate_bullets(
            soap
        )

        self.assertEqual(
            result.count("注射治療を継続する"),
            1,
        )


    def test_assessment_copy_of_objective_is_removed(self):
        soap = (
            "S：\n- 薬は飲んでいる。\n\n"
            "O：\n- 本日の血圧が高い。\n\n"
            "A：\n- 本日の血圧が高い。\n\n"
            "P："
        )

        result = (
            SOAPService.remove_objective_assessment_duplicates(
                soap
            )
        )

        self.assertEqual(
            result.count("本日の血圧が高い"),
            1,
        )
        self.assertIn("O：\n- 本日の血圧が高い", result)
        self.assertIn("A：", result)

    def test_assessment_with_interpretation_is_kept(self):
        soap = (
            "O：\n- 本日の血圧が高い。\n\n"
            "A：\n- 血圧高値で降圧不十分。"
        )

        result = (
            SOAPService.remove_objective_assessment_duplicates(
                soap
            )
        )

        self.assertIn(
            "血圧高値で降圧不十分",
            result,
        )


    def test_paraphrased_blood_pressure_copy_is_removed(self):
        soap = (
            "O：\n- 本日、血圧高値。\n\n"
            "A：\n"
            "- 医師は、今日は血圧がかなり高い"
            "と述べている。"
        )

        result = (
            SOAPService.remove_objective_assessment_duplicates(
                soap
            )
        )

        self.assertIn("O：\n- 本日、血圧高値", result)
        self.assertNotIn("医師は", result)
        self.assertEqual(
            result.count("血圧"),
            1,
        )

    def test_blood_pressure_diagnosis_is_not_removed(self):
        soap = (
            "O：\n- 本日、血圧高値。\n\n"
            "A：\n- 高血圧症として治療中。"
        )

        result = (
            SOAPService.remove_objective_assessment_duplicates(
                soap
            )
        )

        self.assertIn(
            "高血圧症として治療中",
            result,
        )


    def test_report_narration_is_cleaned_before_oa_deduplication(
        self,
    ):
        soap = (
            "S：\n"
            "- 薬をちゃんと飲んでいると回答。\n\n"
            "O：\n"
            "- 本日の血圧が高いとの医師発言あり。\n\n"
            "A：\n"
            "- 本日は血圧が高い。\n\n"
            "P："
        )

        cleaned = SOAPService.remove_report_narration(
            soap
        )
        result = (
            SOAPService.remove_objective_assessment_duplicates(
                cleaned
            )
        )

        self.assertIn(
            "薬をちゃんと飲んでいる。",
            result,
        )
        self.assertIn(
            "本日の血圧が高い。",
            result,
        )
        self.assertNotIn("と回答", result)
        self.assertNotIn("医師発言", result)
        self.assertEqual(
            result.count("血圧"),
            1,
        )


class RecorderWorkflowTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        recorder_path = (
            Path(__file__).resolve().parent
            / "static"
            / "soap"
            / "js"
            / "recorder.js"
        )
        cls.source = recorder_path.read_text(encoding="utf-8")

    def test_realtime_chunk_does_not_generate_soap(self):
        realtime_section = self.source.split(
            "async function handleRealtimeChunk",
            1,
        )[1].split(
            "async function finalizeFullRecording",
            1,
        )[0]

        self.assertNotIn("updateSOAP()", realtime_section)

    def test_final_recording_generates_soap_once(self):
        final_section = self.source.split(
            "async function finalizeFullRecording",
            1,
        )[1].split(
            "async function retryFinalProcessing",
            1,
        )[0]

        self.assertEqual(
            final_section.count("await updateSOAP()"),
            1,
        )
        self.assertIn(
            "await Promise.all(Array.from(activeTranscriptions))",
            final_section,
        )

    def test_realtime_transcriptions_are_rendered_in_order(self):
        self.assertIn(
            "pendingTranscripts.set(sequence, transcript)",
            self.source,
        )
        self.assertIn(
            "flushRealtimeTranscripts()",
            self.source,
        )
        self.assertIn(
            "activeTranscriptions.add(task)",
            self.source,
        )

    def test_realtime_uses_standalone_wav_chunks(self):
        self.assertIn(
            "function encodeWav(samples, sampleRate)",
            self.source,
        )
        self.assertIn(
            "REALTIME_CHUNK_SECONDS = 10",
            self.source,
        )
        self.assertIn(
            '"chunk_" + sequence + ".wav"',
            self.source,
        )
        self.assertNotIn("cumulativeBlob", self.source)
        self.assertIn(
            "conversationChunks.push(transcript)",
            self.source,
        )
        self.assertIn(
            "medicalNote.value += transcript",
            self.source,
        )

    def test_final_webm_and_realtime_wav_are_separate(self):
        self.assertIn(
            'type: "audio/webm;codecs=opus"',
            self.source,
        )
        self.assertIn(
            'new Blob([buffer], { type: "audio/wav" })',
            self.source,
        )
        self.assertIn(
            "await stopRealtimePcmCapture()",
            self.source,
        )

    def test_quiet_audio_is_amplified_for_all_recordings(self):
        self.assertIn(
            "const MICROPHONE_GAIN = 2.5",
            self.source,
        )
        self.assertIn(
            "inputGain.gain.value = MICROPHONE_GAIN",
            self.source,
        )
        self.assertIn(
            "createDynamicsCompressor()",
            self.source,
        )
        self.assertIn(
            "analyserNode.connect(recordingDestination)",
            self.source,
        )
        self.assertIn(
            "noiseSuppression: false",
            self.source,
        )
        self.assertIn(
            "new MediaRecorder(amplifiedStream",
            self.source,
        )
        self.assertIn(
            "autoGainControl: false",
            self.source,
        )

    def test_microphone_device_and_level_are_visible(self):
        self.assertIn(
            'document.getElementById("microphoneDevice")',
            self.source,
        )
        self.assertIn(
            'document.getElementById("audioLevelMeter")',
            self.source,
        )
        self.assertIn(
            "audioLevelMeter.value = percentage",
            self.source,
        )
        self.assertIn(
            "audioTrack.label",
            self.source,
        )
        self.assertIn(
            "analyserNode.getFloatTimeDomainData(samples)",
            self.source,
        )
        self.assertIn(
            'audioLevelText.innerText = "小さい"',
            self.source,
        )

    def test_transcription_receives_intake_and_final_flag(self):
        self.assertIn(
            'formData.append("intake_note", intakeNote.value)',
            self.source,
        )
        self.assertIn(
            'formData.append("is_final", isFinal ? "true" : "false")',
            self.source,
        )

class SessionSafetyWorkflowTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        soap_dir = Path(__file__).resolve().parent

        cls.recorder_source = (
            soap_dir
            / "static"
            / "soap"
            / "js"
            / "recorder.js"
        ).read_text(encoding="utf-8")

        cls.template_source = (
            soap_dir
            / "templates"
            / "soap"
            / "index.html"
        ).read_text(encoding="utf-8")

    def test_session_controls_are_visible(self):
        for element_id in [
            "newSessionBtn",
            "retryFinalBtn",
            "completeSessionBtn",
            "sessionHint",
        ]:
            self.assertIn(
                f'id="{element_id}"',
                self.template_source,
            )

    def test_recording_buttons_follow_explicit_state(self):
        self.assertIn(
            'let sessionState = "idle"',
            self.recorder_source,
        )
        self.assertIn(
            'startBtn.disabled = state !== "idle"',
            self.recorder_source,
        )
        self.assertIn(
            'stopBtn.disabled = state !== "recording"',
            self.recorder_source,
        )
        self.assertIn(
            'newSessionBtn.disabled = isSessionBusy()',
            self.recorder_source,
        )
        self.assertIn(
            'state === "ready"',
            self.recorder_source,
        )

    def test_new_session_requires_confirmation_when_dirty(self):
        session_section = self.recorder_source.split(
            "function startNewSession()",
            1,
        )[1].split(
            "function getCsrfToken()",
            1,
        )[0]

        self.assertIn("sessionDirty", session_section)
        self.assertIn("window.confirm", session_section)
        self.assertIn(
            "resetRecordingBuffers()",
            session_section,
        )
        self.assertIn(
            "clearSessionOutputs()",
            session_section,
        )

    def test_api_failure_keeps_audio_for_retry(self):
        final_section = self.recorder_source.split(
            "async function finalizeFullRecording",
            1,
        )[1].split(
            "async function generateReferral",
            1,
        )[0]

        self.assertIn(
            "retainedFinalBlob = blobOverride || new Blob",
            final_section,
        )
        self.assertIn(
            "retainedFinalTranscript = finalTranscript",
            final_section,
        )
        self.assertIn(
            'setSessionState(\n            "error"',
            final_section,
        )
        self.assertIn(
            "async function retryFinalProcessing()",
            final_section,
        )

    def test_stop_button_is_idempotent(self):
        stop_section = self.recorder_source.split(
            "stopBtn.onclick = function()",
            1,
        )[1].split(
            "[intakeNote, medicalNote, soapResult]",
            1,
        )[0]

        self.assertIn(
            'sessionState !== "recording"',
            stop_section,
        )
        self.assertIn(
            'mediaRecorder.state !== "recording"',
            stop_section,
        )
        self.assertIn(
            'setSessionState(\n        "stopping"',
            stop_section,
        )

    def test_unsaved_or_busy_session_warns_before_unload(self):
        unload_section = self.recorder_source.split(
            'window.addEventListener("beforeunload"',
            1,
        )[1]

        self.assertIn("sessionDirty", unload_section)
        self.assertIn("isSessionBusy()", unload_section)
        self.assertIn("event.preventDefault()", unload_section)
        self.assertIn('event.returnValue = ""', unload_section)

