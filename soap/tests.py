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
            is_final=True,
        )

        self.assertEqual(result, "DigiKar")
        kwargs = (
            mock_client.audio.transcriptions.create.call_args.kwargs
        )
        self.assertEqual(kwargs["prompt"], "脂質異常症、CK")
        service.medical_dictionary.build_transcription_prompt.assert_called_once_with(
            "検査結果"
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
            "async function generateReferral",
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
            "voiceCompressor.connect(recordingDestination)",
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

    def test_transcription_receives_intake_and_final_flag(self):
        self.assertIn(
            'formData.append("intake_note", intakeNote.value)',
            self.source,
        )
        self.assertIn(
            'formData.append("is_final", isFinal ? "true" : "false")',
            self.source,
        )
