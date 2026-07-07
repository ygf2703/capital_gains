from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .auth import AuthService, AuthSession
from .exchange_rates import parse_user_date
from .models import CalculationResult, ExchangeRateSnapshot, Transaction, ValidationIssue
from .parsers import HeaderPreview
from .services import (
    ParsedReports,
    answer_question,
    answer_question_with_evidence,
    calculate_analysis,
    export_analysis,
    parse_reports,
    preview_report_headers,
    save_generic_report_template,
    suggest_questions,
)
from .qa import QAResponse
from .user_identity import UserIdentity, load_user_identity


@dataclass(slots=True)
class AppState:
    files: list[Path] = field(default_factory=list)
    result: CalculationResult | None = None
    exchange_rate: ExchangeRateSnapshot | None = None
    auth_session: AuthSession = field(default_factory=AuthSession)
    user_identity: UserIdentity = field(default_factory=UserIdentity)


@dataclass(slots=True)
class AnalysisPreparation:
    requested_date: date
    transactions: list[Transaction]
    issues: list[ValidationIssue]
    unsupported_headers: list[ValidationIssue]
    previews: list[HeaderPreview]


@dataclass(slots=True)
class ExportOutcome:
    output_path: Path
    result: CalculationResult
    exchange_error: str


class CapitalGainsWorkflow:
    def __init__(self, auth_service: AuthService | None = None) -> None:
        self.auth_service = auth_service or AuthService()
        auth_session = self.auth_service.load_session()
        self.state = AppState(
            auth_session=auth_session,
            user_identity=auth_session.identity if auth_session.email else load_user_identity(),
        )

    def add_files(self, paths: list[str | Path]) -> list[Path]:
        added: list[Path] = []
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
                continue
            if path in self.state.files:
                continue
            self.state.files.append(path)
            added.append(path)
        return added

    def clear_files(self) -> None:
        self.state.files.clear()
        self.state.result = None

    def has_google_configuration(self) -> bool:
        return self.auth_service.has_google_configuration()

    def sign_in_with_google(self) -> AuthSession:
        session = self.auth_service.sign_in_with_google()
        self.state.auth_session = session
        self.state.user_identity = session.identity if session.email else load_user_identity()
        return session

    def sign_in_local(self, email: str, password: str, remember: bool = True) -> AuthSession:
        session = self.auth_service.sign_in_local(email, password, remember=remember)
        self.state.auth_session = session
        self.state.user_identity = session.identity if session.email else load_user_identity()
        return session

    def register_local_user(self, name: str, email: str, password: str, remember: bool = True) -> AuthSession:
        session = self.auth_service.register_local_user(name, email, password, remember=remember)
        self.state.auth_session = session
        self.state.user_identity = session.identity if session.email else load_user_identity()
        return session

    def sign_out(self) -> None:
        self.auth_service.sign_out()
        self.state.auth_session = AuthSession()
        self.state.user_identity = load_user_identity()

    def preview_current_headers(self) -> list[HeaderPreview]:
        return preview_report_headers(self.state.files)

    def save_generic_template(self, name: str, field_map: dict[str, str]) -> None:
        save_generic_report_template(name, field_map)

    def fetch_exchange_rate(self, requested_date: date) -> ExchangeRateSnapshot:
        from .exchange_rates import fetch_usd_ils_rate_one_month_back

        rate = fetch_usd_ils_rate_one_month_back(requested_date)
        self.state.exchange_rate = rate
        return rate

    def prepare_analysis(self, exchange_date: str) -> AnalysisPreparation:
        if not self.state.files:
            raise ValueError("יש לבחור לפחות קובץ אקסל אחד.")

        requested_date = parse_user_date(exchange_date)
        parsed: ParsedReports = parse_reports(self.state.files)
        unsupported_headers = [issue for issue in parsed.issues if issue.field == "header" and issue.severity == "error"]
        previews = self.preview_current_headers() if unsupported_headers else []
        return AnalysisPreparation(
            requested_date=requested_date,
            transactions=parsed.transactions,
            issues=parsed.issues,
            unsupported_headers=unsupported_headers,
            previews=previews,
        )

    def export(
        self,
        transactions: list[Transaction],
        issues: list[ValidationIssue],
        output: str,
        requested_date: date,
    ) -> ExportOutcome:
        exchange_error = ""
        exchange_rate = self.state.exchange_rate
        if exchange_rate is None or exchange_rate.requested_date != requested_date:
            try:
                exchange_rate = self.fetch_exchange_rate(requested_date)
            except Exception as exc:
                exchange_error = str(exc)
                exchange_rate = None

        result = calculate_analysis(transactions, issues)
        result.exchange_rate = exchange_rate
        path = export_analysis(result, output)
        self.state.result = result
        if result.exchange_rate:
            self.state.exchange_rate = result.exchange_rate
        return ExportOutcome(output_path=path, result=result, exchange_error=exchange_error)

    def answer_question(self, question: str) -> str:
        return answer_question(self.state.result, question)

    def answer_question_with_evidence(self, question: str) -> QAResponse:
        return answer_question_with_evidence(self.state.result, question)

    def suggest_questions(self) -> list[str]:
        return suggest_questions(self.state.result)
