import json
import unittest
from pathlib import Path

from capital_gains_app.user_identity import UserIdentity, display_name_from_email, greeting_for_user, load_user_identity


class UserIdentityTests(unittest.TestCase):
    def test_display_name_is_derived_from_email_local_part(self) -> None:
        self.assertEqual(display_name_from_email("liat.cohen@gmail.com"), "Liat")
        self.assertEqual(display_name_from_email("noam-finance@example.com"), "Noam")

    def test_display_name_keeps_hebrew_email_name(self) -> None:
        self.assertEqual(display_name_from_email("ליאת@example.com"), "ליאת")

    def test_explicit_google_name_wins_over_email(self) -> None:
        identity = UserIdentity(email="liat.cohen@gmail.com", name="ליאת כהן")

        self.assertEqual(identity.display_name, "ליאת כהן")
        self.assertEqual(greeting_for_user(identity), "היי ליאת כהן, יש קבצים לניתוח?")

    def test_profile_loader_reads_future_google_profile(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.json"
            profile.write_text(json.dumps({"email": "liat.cohen@gmail.com"}), encoding="utf-8")

            self.assertEqual(load_user_identity(profile).display_name, "Liat")


if __name__ == "__main__":
    unittest.main()
