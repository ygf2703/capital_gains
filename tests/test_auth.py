from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from capital_gains_app.auth import (
    GOOGLE_CLIENT_SECRET_ENV,
    AuthService,
    AuthSession,
    DuplicateUserError,
    GoogleAuthService,
    InvalidCredentialsError,
)


class AuthServiceTests(unittest.TestCase):
    def test_google_client_secret_candidates_prefer_env_then_repo_and_local(self) -> None:
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            service = GoogleAuthService(profile_path=profile_path)

            self.addCleanup(self._clear_env)
            import os

            os.environ[GOOGLE_CLIENT_SECRET_ENV] = str(Path(tmp) / "custom.json")
            candidates = service.client_secret_candidates()

            self.assertEqual(candidates[0], Path(tmp) / "custom.json")
            self.assertIn(profile_path.with_name("google_client_secret.json"), candidates)

    def test_load_session_reads_google_profile_even_when_token_needs_reauth(self) -> None:
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            token_path = Path(tmp) / "google_token.json"
            token_path.write_text("{}", encoding="utf-8")
            profile_path.write_text(
                '{"provider":"google","email":"liat.cohen@gmail.com","name":"Liat","picture":"https://example.com/p.png"}',
                encoding="utf-8",
            )

            session = GoogleAuthService(profile_path=profile_path, token_path=token_path).load_session()

            self.assertFalse(session.connected)
            self.assertEqual(session.email, "liat.cohen@gmail.com")
            self.assertEqual(session.identity.display_name, "Liat")

    def test_local_registration_and_login_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            users_path = Path(tmp) / "users.json"
            auth = AuthService(profile_path=profile_path, users_path=users_path, token_path=Path(tmp) / "token.json")

            session = auth.register_local_user("Liat Cohen", "Liat.Cohen@gmail.com", "secret12", remember=True)
            logged_in = auth.sign_in_local("liat.cohen@gmail.com", "secret12", remember=False)

            self.assertEqual(session.provider, "local")
            self.assertEqual(logged_in.email, "liat.cohen@gmail.com")
            self.assertEqual(auth.load_session().email, "liat.cohen@gmail.com")

    def test_duplicate_local_registration_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            auth = AuthService(
                profile_path=Path(tmp) / "profile.json",
                users_path=Path(tmp) / "users.json",
                token_path=Path(tmp) / "token.json",
            )
            auth.register_local_user("Liat Cohen", "liat@gmail.com", "secret12")

            with self.assertRaises(DuplicateUserError):
                auth.register_local_user("Liat Cohen", "liat@gmail.com", "secret12")

    def test_invalid_local_password_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            auth = AuthService(
                profile_path=Path(tmp) / "profile.json",
                users_path=Path(tmp) / "users.json",
                token_path=Path(tmp) / "token.json",
            )
            auth.register_local_user("Liat Cohen", "liat@gmail.com", "secret12")

            with self.assertRaises(InvalidCredentialsError):
                auth.sign_in_local("liat@gmail.com", "wrongpass")

    def test_sign_out_clears_local_profile_but_keeps_user_store(self) -> None:
        with TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            users_path = Path(tmp) / "users.json"
            auth = AuthService(profile_path=profile_path, users_path=users_path, token_path=Path(tmp) / "token.json")
            auth.register_local_user("Liat Cohen", "liat@gmail.com", "secret12")

            auth.sign_out()

            self.assertFalse(profile_path.exists())
            self.assertTrue(users_path.exists())

    def test_auth_session_exposes_user_identity(self) -> None:
        session = AuthSession(provider="google", email="liat.cohen@gmail.com", name="Liat", connected=True)

        self.assertEqual(session.identity.email, "liat.cohen@gmail.com")
        self.assertEqual(session.identity.display_name, "Liat")

    @staticmethod
    def _clear_env() -> None:
        import os

        os.environ.pop(GOOGLE_CLIENT_SECRET_ENV, None)


if __name__ == "__main__":
    unittest.main()
