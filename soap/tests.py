import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase

from .services.soap_service import SOAPService
from .services.speech_service import SpeechService
from .services.visit_analyzer_service import VisitAnalyzerService
from .services.clinical_record_validator import ClinicalRecordValidator


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


class SpeakerDiarizationReliabilityTests(SimpleTestCase):
    def test_question_and_short_answer_are_dialogue_evidence(self):
        transcript = (
            "話者A：お薬は飲んでいますか？\n"
            "話者A：はい。"
        )

        self.assertTrue(
            SpeechService.has_dialogue_evidence(
                transcript
            )
        )
        self.assertFalse(
            SpeechService.has_dialogue_evidence(
                "話者A：本日の検査結果を説明します。"
            )
        )

    @patch("soap.services.speech_service.client")
    def test_single_speaker_labels_are_repaired_without_text_change(
        self,
        mock_client,
    ):
        mock_client.responses.create.return_value = (
            SimpleNamespace(
                output_text=(
                    "話者A：お薬は飲んでいますか？\n"
                    "話者B：はい。"
                )
            )
        )
        service = SpeechService.__new__(SpeechService)

        result = service.repair_single_speaker_diarization(
            accurate_text=(
                "お薬は飲んでいますか？はい。"
            ),
            diarized_text=(
                "話者A：お薬は飲んでいますか？\n"
                "話者A：はい。"
            ),
        )

        self.assertEqual(
            result,
            "話者A：お薬は飲んでいますか？\n"
            "話者B：はい。",
        )

    @patch("soap.services.speech_service.client")
    def test_repair_is_rejected_when_spoken_words_change(
        self,
        mock_client,
    ):
        mock_client.responses.create.return_value = (
            SimpleNamespace(
                output_text=(
                    "話者A：お薬は飲んでいますか？\n"
                    "話者B：いいえ。"
                )
            )
        )
        service = SpeechService.__new__(SpeechService)

        result = service.repair_single_speaker_diarization(
            accurate_text=(
                "お薬は飲んでいますか？はい。"
            ),
            diarized_text=(
                "話者A：お薬は飲んでいますか？\n"
                "話者A：はい。"
            ),
        )

        self.assertEqual(result, "")

    @patch("soap.services.speech_service.client")
    def test_final_transcription_repairs_single_speaker_dialogue(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.side_effect = [
            SimpleNamespace(
                text="お薬は飲んでいますか？はい。"
            ),
            SimpleNamespace(
                segments=[
                    SimpleNamespace(
                        speaker="speaker_0",
                        text="お薬は飲んでいますか？",
                    ),
                    SimpleNamespace(
                        speaker="speaker_0",
                        text="はい。",
                    ),
                ]
            ),
        ]
        mock_client.responses.create.side_effect = [
            SimpleNamespace(
                output_text=(
                    "話者A：お薬は飲んでいますか？\n"
                    "話者B：はい。"
                )
            ),
            SimpleNamespace(
                output_text=(
                    "話者A：お薬は飲んでいますか？\n"
                    "話者B：はい。"
                )
            ),
        ]
        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            ""
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
            is_final=True,
        )

        self.assertEqual(
            result,
            "話者A：お薬は飲んでいますか？\n"
            "話者B：はい。",
        )
        self.assertEqual(
            mock_client.responses.create.call_count,
            2,
        )

    @patch("soap.services.speech_service.client")
    def test_merge_cannot_collapse_multiple_speakers(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.side_effect = [
            SimpleNamespace(
                text="体調はどうですか？変わりません。"
            ),
            SimpleNamespace(
                segments=[
                    SimpleNamespace(
                        speaker="speaker_0",
                        text="体調はどうですか？",
                    ),
                    SimpleNamespace(
                        speaker="speaker_1",
                        text="変わりません。",
                    ),
                ]
            ),
        ]
        mock_client.responses.create.return_value = (
            SimpleNamespace(
                output_text=(
                    "話者A：体調はどうですか？\n"
                    "話者A：変わりません。"
                )
            )
        )
        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            ""
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
            is_final=True,
        )

        self.assertEqual(
            result,
            "話者A：体調はどうですか？\n"
            "話者B：変わりません。",
        )

    @patch("soap.services.speech_service.client")
    def test_single_speaker_monologue_uses_accurate_text(
        self,
        mock_client,
    ):
        mock_client.audio.transcriptions.create.side_effect = [
            SimpleNamespace(
                text="本日の検査結果を説明します。"
            ),
            SimpleNamespace(
                segments=[
                    SimpleNamespace(
                        speaker="speaker_0",
                        text="本日の検査結果を説明します。",
                    )
                ]
            ),
        ]
        service = SpeechService.__new__(SpeechService)
        service.medical_dictionary = Mock()
        service.medical_dictionary.build_transcription_prompt.return_value = (
            ""
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
            is_final=True,
        )

        self.assertEqual(
            result,
            "本日の検査結果を説明します。",
        )
        mock_client.responses.create.assert_not_called()


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

class ClinicalRecordValidatorTests(SimpleTestCase):
    def setUp(self):
        self.validator = ClinicalRecordValidator()

    @staticmethod
    def by_item(checks, text):
        return next(
            check
            for check in checks
            if text in check["item"]
        )

    def test_supported_record_passes_all_quality_checks(self):
        source = (
            "話者A：血圧は125です。\n"
            "話者B：薬は飲んでいます。"
        )
        encounter = {
            "encounter": {
                "patient_answers": [
                    "薬は飲んでいる"
                ]
            }
        }
        soap = (
            "S：\n- 薬は飲んでいる。\n\n"
            "O：\n- 血圧125。\n\n"
            "A：\n\nP："
        )

        checks = self.validator.validate(
            source,
            encounter,
            soap,
        )

        quality_checks = [
            check
            for check in checks
            if check["category"] == "記録品質"
        ]
        self.assertEqual(len(quality_checks), 5)
        self.assertTrue(
            all(
                check["checked"]
                for check in quality_checks
            )
        )

    def test_number_not_found_in_source_is_flagged(self):
        checks = self.validator.validate(
            source_note="血圧は高いです。",
            encounter={},
            soap_text="O：\n- 血圧180。",
        )

        check = self.by_item(
            checks,
            "原文にない数値",
        )

        self.assertFalse(check["checked"])
        self.assertEqual(check["level"], "high")
        self.assertIn("180", check["item"])

    def test_unknown_marker_in_soap_is_flagged(self):
        checks = self.validator.validate(
            source_note="聞き取り不明",
            encounter={},
            soap_text=(
                "S：\n- ［聞き取り不明］"
            ),
        )

        check = self.by_item(
            checks,
            "聞き取り不明語",
        )

        self.assertFalse(check["checked"])

    def test_objective_assessment_duplicate_is_flagged(self):
        checks = self.validator.validate(
            source_note="今日は血圧が高い。",
            encounter={},
            soap_text=(
                "O：\n- 本日、血圧高値。\n\n"
                "A：\n- 今日は血圧が高い。"
            ),
        )

        check = self.by_item(
            checks,
            "OとA",
        )

        self.assertFalse(check["checked"])
        self.assertIn(
            "今日は血圧が高い",
            check["item"],
        )

    def test_meta_narration_is_flagged(self):
        checks = self.validator.validate(
            source_note="薬は飲んでいます。",
            encounter={
                "encounter": {
                    "patient_answers": [
                        "薬は飲んでいる"
                    ]
                }
            },
            soap_text=(
                "S：\n- 薬は飲んでいると回答。"
            ),
        )

        check = self.by_item(
            checks,
            "メタ表現",
        )

        self.assertFalse(check["checked"])
        self.assertIn("と回答", check["item"])

    def test_subjective_without_patient_evidence_is_flagged(self):
        checks = self.validator.validate(
            source_note=(
                "話者A：筋肉痛はないですか。"
            ),
            encounter={
                "encounter": {
                    "patient_answers": []
                },
                "subjective_symptoms": [],
            },
            soap_text="S：\n- 筋肉痛なし。",
        )

        check = self.by_item(
            checks,
            "Sの患者回答",
        )

        self.assertFalse(check["checked"])

    def test_intake_subjective_supports_soap_subjective(self):
        checks = self.validator.validate(
            source_note="受付問診：咳",
            encounter={
                "intake": {
                    "chief_complaint": "咳",
                    "history": [],
                    "subjective_symptoms": ["咳"],
                }
            },
            soap_text="S：\n- 咳あり。",
        )

        check = self.by_item(
            checks,
            "Sの患者回答",
        )

        self.assertTrue(check["checked"])



class SecurityAndPrivacyTests(SimpleTestCase):
    def test_clinical_api_rejects_post_without_csrf_token(self):
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            "/transcribe_chunk/",
            {},
        )

        self.assertEqual(response.status_code, 403)

    def test_valid_csrf_token_reaches_clinical_api(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/")
        token = client.cookies["csrftoken"].value

        response = client.post(
            "/transcribe_chunk/",
            {},
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "音声ファイルがありません",
        )

    @patch("soap.views.SpeechService")
    def test_transcription_error_hides_internal_details(
        self,
        speech_service_class,
    ):
        speech_service_class.return_value.transcribe_audio.side_effect = (
            RuntimeError("secret provider detail")
        )
        audio = SimpleUploadedFile(
            "recording.wav",
            b"not-real-audio",
            content_type="audio/wav",
        )

        response = self.client.post(
            "/transcribe_chunk/",
            {
                "audio_file": audio,
                "is_final": "true",
            },
        )
        payload = response.json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            payload["error_code"],
            "TRANSCRIPTION_FAILED",
        )
        self.assertNotIn(
            "secret provider detail",
            payload["error"],
        )

    @patch(
        "soap.views.analyze_visit",
        side_effect=RuntimeError("secret prompt detail"),
    )
    def test_soap_error_hides_internal_details(
        self,
        _analyze_visit,
    ):
        response = self.client.post(
            "/generate_soap/",
            {"medical_note": "診察内容"},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            payload["error_code"],
            "SOAP_GENERATION_FAILED",
        )
        self.assertNotIn(
            "secret prompt detail",
            payload["error"],
        )

    @patch(
        "soap.views.analyze_visit",
        side_effect=RuntimeError("secret referral detail"),
    )
    def test_referral_error_hides_internal_details(
        self,
        _analyze_visit,
    ):
        response = self.client.post(
            "/generate_referral/",
            {"medical_note": "診察内容"},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            payload["error_code"],
            "REFERRAL_GENERATION_FAILED",
        )
        self.assertNotIn(
            "secret referral detail",
            payload["error"],
        )

    def test_recording_confirmation_is_required_and_reset(self):
        soap_dir = Path(__file__).resolve().parent
        template = (
            soap_dir
            / "templates"
            / "soap"
            / "index.html"
        ).read_text(encoding="utf-8")
        recorder = (
            soap_dir
            / "static"
            / "soap"
            / "js"
            / "recorder.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'id="recordingConsent"',
            template,
        )
        self.assertIn(
            "患者さんへの録音・AI処理の説明",
            template,
        )
        self.assertIn(
            "startBtn.disabled = !recordingConsent.checked",
            recorder,
        )
        self.assertIn(
            "recordingConsent.checked = false",
            recorder,
        )
        self.assertIn(
            "|| !recordingConsent.checked",
            recorder,
        )

    def test_csrf_token_comes_from_rendered_form(self):
        recorder = (
            Path(__file__).resolve().parent
            / "static"
            / "soap"
            / "js"
            / "recorder.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '"[name=csrfmiddlewaretoken]"',
            recorder,
        )
        self.assertIn(
            'headers: {\n            "X-CSRFToken": getCsrfToken()',
            recorder,
        )

    def test_environment_example_contains_no_real_secret(self):
        example = (
            Path(__file__).resolve().parent.parent
            / ".env.example"
        ).read_text(encoding="utf-8")

        for key in [
            "OPENAI_API_KEY",
            "DJANGO_SECRET_KEY",
            "DJANGO_PRODUCTION",
            "DJANGO_ALLOWED_HOSTS",
            "DJANGO_HTTPS",
        ]:
            self.assertIn(key, example)

        self.assertNotIn("sk-", example)


class OperationsReadinessTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.start_script = (
            cls.root_dir / "start_aiclinic.bat"
        ).read_text(encoding="utf-8")
        cls.setup_script = (
            cls.root_dir / "setup_aiclinic.bat"
        ).read_text(encoding="utf-8")
        cls.backup_script = (
            cls.root_dir / "backup_aiclinic.bat"
        ).read_text(encoding="utf-8")

    def test_health_endpoint_exposes_no_configuration(self):
        response = self.client.get("/health/")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "AIClinic")

        serialized = json.dumps(payload)
        self.assertNotIn("key", serialized.lower())
        self.assertNotIn("database", serialized.lower())
        self.assertIn(
            "no-cache",
            response.headers["Cache-Control"],
        )

    def test_health_endpoint_is_get_only(self):
        response = self.client.post("/health/")

        self.assertEqual(response.status_code, 405)

    def test_windows_scripts_select_utf8_code_page(self):
        for script in [
            self.setup_script,
            self.start_script,
            self.backup_script,
        ]:
            self.assertIn(
                "chcp 65001 >nul",
                script,
            )
            self.assertEqual(
                script,
                script.encode("ascii").decode("ascii"),
            )

    def test_start_script_uses_waitress_on_loopback_only(self):
        self.assertIn(
            "waitress-serve.exe",
            self.start_script,
        )
        self.assertIn(
            "--listen=127.0.0.1:8000",
            self.start_script,
        )
        self.assertIn(
            "--no-expose-tracebacks",
            self.start_script,
        )
        self.assertNotIn("0.0.0.0", self.start_script)
        self.assertNotIn("manage.py runserver", self.start_script)
        self.assertIn(
            "manage.py collectstatic --noinput",
            self.start_script,
        )
        self.assertLess(
            self.start_script.index(
                "manage.py collectstatic --noinput"
            ),
            self.start_script.rindex(
                "waitress-serve.exe"
            ),
        )

    def test_setup_prepares_complete_production_runtime(self):
        for command in [
            "scripts\\configure_production.py",
            "requirements-production.txt",
            "manage.py migrate",
            "manage.py collectstatic --noinput",
            "manage.py check --deploy --fail-level ERROR",
        ]:
            self.assertIn(command, self.setup_script)

    def test_production_dependencies_are_pinned(self):
        requirements = (
            self.root_dir / "requirements-production.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("waitress==3.0.2", requirements)
        self.assertIn("whitenoise==6.12.0", requirements)

    def test_production_static_files_are_conditional(self):
        settings_source = (
            self.root_dir
            / "clinic"
            / "settings.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "if PRODUCTION_MODE:",
            settings_source,
        )
        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware",
            settings_source,
        )
        self.assertIn(
            "CompressedStaticFilesStorage",
            settings_source,
        )

    def test_logs_do_not_include_exception_tracebacks(self):
        views_source = (
            Path(__file__).resolve().parent
            / "views.py"
        ).read_text(encoding="utf-8")
        speech_source = (
            Path(__file__).resolve().parent
            / "services"
            / "speech_service.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("logger.exception", views_source)
        self.assertNotIn("logger.exception", speech_source)
        self.assertIn(
            'logger.error("SOAP generation failed")',
            views_source,
        )

    def test_backups_and_generated_files_are_not_committed(self):
        gitignore = (
            self.root_dir / ".gitignore"
        ).read_text(encoding="utf-8")
        backup_source = (
            self.root_dir
            / "scripts"
            / "backup_database.py"
        ).read_text(encoding="utf-8")

        self.assertIn("backups/", gitignore)
        self.assertIn("staticfiles/", gitignore)
        self.assertIn("KEEP_BACKUPS = 14", backup_source)

    def test_operations_guide_warns_about_unsaved_records(self):
        guide = (
            self.root_dir
            / "docs"
            / "clinic_operations.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "未転記の",
            guide,
        )
        self.assertIn(
            "0.0.0.0",
            guide,
        )
        self.assertIn(
            "実患者",
            guide,
        )


class SessionRecoveryWorkflowTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_dir = Path(__file__).resolve().parent.parent
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

    def test_recovery_notice_and_discard_control_are_visible(self):
        self.assertIn(
            'id="recoveryNotice"',
            self.template_source,
        )
        self.assertIn(
            'id="discardRecoveryBtn"',
            self.template_source,
        )
        self.assertIn(
            "録音音声は保存されていません",
            self.template_source,
        )

    def test_recovery_uses_tab_scoped_storage_with_expiry(self):
        self.assertIn(
            'RECOVERY_STORAGE_KEY = '
            '"aiclinic.unsavedEncounter.v1"',
            self.recorder_source,
        )
        self.assertIn(
            "RECOVERY_MAX_AGE_MS = 12 * 60 * 60 * 1000",
            self.recorder_source,
        )
        self.assertIn(
            "sessionStorage.setItem",
            self.recorder_source,
        )
        self.assertIn(
            "sessionStorage.getItem",
            self.recorder_source,
        )
        self.assertNotIn(
            "localStorage",
            self.recorder_source,
        )

    def test_recovery_payload_contains_text_but_not_audio(self):
        payload_section = self.recorder_source.split(
            "const payload = {",
            1,
        )[1].split(
            "};",
            1,
        )[0]

        for field in [
            "intakeNote",
            "medicalNote",
            "soapResult",
            "encounterJson",
            "referralResult",
            "conversationChunks",
        ]:
            self.assertIn(field, payload_section)

        for forbidden in [
            "retainedFinalBlob",
            "fullAudioChunks",
            "apiKey",
            "csrf",
        ]:
            self.assertNotIn(forbidden, payload_section)

    def test_recovery_restores_all_saved_text_fields(self):
        restore_section = self.recorder_source.split(
            "function restoreRecoveryDraft()",
            1,
        )[1].split(
            "function discardRecoveredDraft()",
            1,
        )[0]

        for assignment in [
            "intakeNote.value =",
            "medicalNote.value =",
            "soapResult.value =",
            "encounterJson.value =",
            "referralResult.value =",
            "conversationChunks =",
        ]:
            self.assertIn(assignment, restore_section)

        self.assertIn(
            "age > RECOVERY_MAX_AGE_MS",
            restore_section,
        )

    def test_interrupted_recording_warns_audio_is_not_restored(self):
        restore_section = self.recorder_source.split(
            "function restoreRecoveryDraft()",
            1,
        )[1].split(
            "function discardRecoveredDraft()",
            1,
        )[0]

        self.assertIn("draft.wasBusy", restore_section)
        self.assertIn(
            "録音音声は保存されていません",
            restore_section,
        )

    def test_recovery_is_cleared_after_clinical_handoff(self):
        new_session_section = self.recorder_source.split(
            "function startNewSession()",
            1,
        )[1].split(
            "function getCsrfToken()",
            1,
        )[0]
        completion_section = self.recorder_source.split(
            "completeSessionBtn.onclick",
            1,
        )[1].split(
            "startBtn.onclick",
            1,
        )[0]
        discard_section = self.recorder_source.split(
            "function discardRecoveredDraft()",
            1,
        )[1].split(
            "function markSessionDirty()",
            1,
        )[0]

        self.assertIn(
            "clearRecoveryDraft()",
            new_session_section,
        )
        self.assertIn(
            "clearRecoveryDraft()",
            completion_section,
        )
        self.assertIn(
            "clearRecoveryDraft()",
            discard_section,
        )

    def test_generated_outputs_are_saved_for_recovery(self):
        self.assertGreaterEqual(
            self.recorder_source.count(
                "persistRecoveryDraft();"
            ),
            4,
        )
        self.assertIn(
            'medicalNote.value += transcript + "\\n";\n'
            "            markSessionDirty();",
            self.recorder_source,
        )
        referral_section = self.recorder_source.split(
            "if (data.referral_result)",
            1,
        )[1].split(
            "if (data.error)",
            1,
        )[0]
        self.assertIn(
            "persistRecoveryDraft()",
            referral_section,
        )

    def test_beforeunload_saves_draft_before_warning(self):
        unload_section = self.recorder_source.split(
            'window.addEventListener("beforeunload"',
            1,
        )[1]

        persist_position = unload_section.index(
            "persistRecoveryDraft()"
        )
        warning_position = unload_section.index(
            "event.preventDefault()"
        )
        self.assertLess(
            persist_position,
            warning_position,
        )

    def test_operations_guide_describes_recovery_limits(self):
        guide = (
            self.root_dir
            / "docs"
            / "clinic_operations.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "未転記データの一時復元",
            guide,
        )
        self.assertIn("12時間", guide)
        self.assertIn(
            "ブラウザーやPCを完全に終了した場合"
            "の復元は保証されません",
            guide,
        )
