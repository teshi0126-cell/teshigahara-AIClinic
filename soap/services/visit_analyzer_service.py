import json
from typing import Any

from .openai_service import OpenAIService
from soap.prompts.visit_analyzer_prompt import (
    VISIT_ANALYZER_SYSTEM_PROMPT,
)


class VisitAnalyzerService:
    ALLOWED_VISIT_TYPES = {
        "acute_problem",
        "chronic_followup",
        "test_result_review",
        "medication_refill",
        "health_check_review",
        "referral_consultation",
        "procedure_or_test",
        "preventive_care",
        "other",
    }

    ALLOWED_STATUSES = {
        "new",
        "ongoing",
        "improved",
        "stable",
        "unclear",
    }

    ALLOWED_RELEVANCE = {
        "active",
        "incidental",
    }

    def __init__(self):
        self.ai = OpenAIService()

    def analyze(
        self,
        intake_note: str,
        conversation_text: str,
    ) -> dict[str, Any]:
        intake = (intake_note or "").strip()
        conversation = (conversation_text or "").strip()

        if not intake and not conversation:
            return self.empty_result()

        prompt = f"""
{VISIT_ANALYZER_SYSTEM_PROMPT}

【受付問診】
{intake}

【診察会話】
{conversation}
"""

        raw_result = self.ai.generate_text(prompt)

        try:
            parsed = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            return self.empty_result(
                error="Visit AnalyzerのJSON解析に失敗しました。"
            )

        return self.validate_result(parsed)

    def validate_result(
        self,
        data: Any,
    ) -> dict[str, Any]:
        if not isinstance(data, dict):
            return self.empty_result(
                error="Visit Analyzerの出力形式が不正です。"
            )

        visit_types = self.clean_visit_types(
            data.get("visit_type", [])
        )

        raw_problems = data.get("problems", [])

        if not isinstance(raw_problems, list):
            raw_problems = []

        problems = []

        for raw_problem in raw_problems:
            problem = self.validate_problem(raw_problem)

            if problem is not None:
                problems.append(problem)

        discarded = self.clean_list(
            data.get("discarded_conversation", [])
        )

        visit_summary = data.get("visit_summary")

        if visit_summary is not None:
            visit_summary = (
                str(visit_summary).strip() or None
            )

        return {
            "visit_type": visit_types,
            "visit_summary": visit_summary,
            "problems": problems,
            "discarded_conversation": discarded,
        }

    def clean_visit_types(
        self,
        value: Any,
    ) -> list[str]:
        if not isinstance(value, list):
            return []

        result = []

        for item in value:
            visit_type = str(item).strip()

            if (
                visit_type in self.ALLOWED_VISIT_TYPES
                and visit_type not in result
            ):
                result.append(visit_type)

        return result

    def validate_problem(
        self,
        raw_problem: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(raw_problem, dict):
            return None

        title = str(
            raw_problem.get("title", "")
        ).strip()

        if not title:
            return None

        status = str(
            raw_problem.get("status", "unclear")
        ).strip()

        if status not in self.ALLOWED_STATUSES:
            status = "unclear"

        relevance = str(
            raw_problem.get("relevance", "active")
        ).strip()

        if relevance not in self.ALLOWED_RELEVANCE:
            relevance = "active"

        raw_include = raw_problem.get(
            "include_in_soap",
            relevance == "active",
        )

        include_in_soap = self.to_boolean(
            raw_include,
            default=(relevance == "active"),
        )

        if relevance == "incidental":
            include_in_soap = bool(include_in_soap)

        return {
            "title": title,
            "status": status,
            "relevance": relevance,
            "include_in_soap": include_in_soap,
            "subjective": self.clean_list(
                raw_problem.get("subjective")
            ),
            "objective": self.clean_list(
                raw_problem.get("objective")
            ),
            "assessment": self.clean_list(
                raw_problem.get("assessment")
            ),
            "plan": self.clean_list(
                raw_problem.get("plan")
            ),
            "patient_education": self.clean_list(
                raw_problem.get("patient_education")
            ),
            "evidence": self.clean_list(
                raw_problem.get("evidence")
            ),
        }

    @staticmethod
    def clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        result = []

        for item in value:
            text = str(item).strip()

            if text and text not in result:
                result.append(text)

        return result

    @staticmethod
    def to_boolean(
        value: Any,
        default: bool = False,
    ) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()

            if normalized in {
                "true",
                "1",
                "yes",
                "on",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "off",
            }:
                return False

        if isinstance(value, (int, float)):
            return bool(value)

        return default

    @staticmethod
    def empty_result(
        error: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "visit_type": [],
            "visit_summary": None,
            "problems": [],
            "discarded_conversation": [],
        }

        if error:
            result["error"] = error

        return result