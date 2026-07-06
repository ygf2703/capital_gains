from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from capital_gains_app.application import CapitalGainsWorkflow
from capital_gains_app.auth import GoogleAuthService


class ApplicationWorkflowTests(unittest.TestCase):
    def test_add_files_deduplicates_excel_inputs(self) -> None:
        with TemporaryDirectory() as tmp:
            auth = GoogleAuthService(profile_path=Path(tmp) / "profile.json", token_path=Path(tmp) / "token.json")
            workflow = CapitalGainsWorkflow(auth_service=auth)
            sample = Path(tmp) / "sample.xlsx"
            sample.touch()

            added = workflow.add_files([sample, sample, Path(tmp) / "notes.txt"])

            self.assertEqual(added, [sample])
            self.assertEqual(workflow.state.files, [sample])

    def test_prepare_analysis_parses_generic_report(self) -> None:
        with TemporaryDirectory() as tmp:
            auth = GoogleAuthService(profile_path=Path(tmp) / "profile.json", token_path=Path(tmp) / "token.json")
            workflow = CapitalGainsWorkflow(auth_service=auth)
            workbook_path = Path(tmp) / "generic.xlsx"

            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["Intro", "", "", "", "", ""])
            sheet.append(["Trade Date", "Transaction Type", "Ticker", "Units", "Unit Price", "Amount"])
            sheet.append(["2024-03-01", "Buy", "MSFT", 3, 200.0, -600.0])
            workbook.save(workbook_path)

            workflow.add_files([workbook_path])
            preparation = workflow.prepare_analysis("2026-06-29")

            self.assertEqual(preparation.requested_date.isoformat(), "2026-06-29")
            self.assertEqual(len(preparation.transactions), 1)
            self.assertFalse(preparation.unsupported_headers)
            self.assertEqual(preparation.transactions[0].symbol, "MSFT")

    def test_answer_question_uses_state_result(self) -> None:
        with TemporaryDirectory() as tmp:
            auth = GoogleAuthService(profile_path=Path(tmp) / "profile.json", token_path=Path(tmp) / "token.json")
            workflow = CapitalGainsWorkflow(auth_service=auth)

            answer = workflow.answer_question("כמה תנועות יש?")

            self.assertIn("קודם צריך לנתח", answer)


if __name__ == "__main__":
    unittest.main()
