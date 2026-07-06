from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from .ui_text import app_root
from .user_identity import UserIdentity, default_profile_path, display_name_from_email


GOOGLE_CLIENT_SECRET_ENV = "CAPITAL_GAINS_GOOGLE_CLIENT_SECRET"
GOOGLE_SCOPES = ("openid", "email", "profile")
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
PBKDF2_ITERATIONS = 240_000


class GoogleAuthError(RuntimeError):
    """Raised when the local Google sign-in flow fails."""


class AuthConfigurationError(GoogleAuthError):
    """Raised when the app is missing Google OAuth client configuration."""


class LocalAuthError(RuntimeError):
    """Raised when local email/password authentication fails."""


class DuplicateUserError(LocalAuthError):
    """Raised when trying to register an email that already exists."""


class InvalidCredentialsError(LocalAuthError):
    """Raised when email/password pair is invalid."""


class WeakPasswordError(LocalAuthError):
    """Raised when a password does not meet minimum policy."""


@dataclass(frozen=True, slots=True)
class AuthSession:
    provider: str = ""
    email: str = ""
    name: str = ""
    picture: str = ""
    connected: bool = False
    user_id: str = ""

    @property
    def identity(self) -> UserIdentity:
        return UserIdentity(email=self.email, name=self.name)


@dataclass(frozen=True, slots=True)
class LocalUserAccount:
    user_id: str
    email: str
    name: str
    password_hash: str
    password_salt: str
    created_at: str


def default_users_path() -> Path:
    return default_profile_path().with_name("users.json")


class LocalUserAuthService:
    def __init__(self, profile_path: Path | None = None, users_path: Path | None = None) -> None:
        self.profile_path = profile_path or default_profile_path()
        self.users_path = users_path or default_users_path()

    def register_user(self, name: str, email: str, password: str, remember: bool = True) -> AuthSession:
        cleaned_name = " ".join(name.strip().split())
        cleaned_email = _normalize_email(email)
        self._validate_registration(cleaned_name, cleaned_email, password)

        users = self._read_users()
        if any(user.email == cleaned_email for user in users):
            raise DuplicateUserError("כבר קיים משתמש עם כתובת האימייל הזו.")

        salt = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        account = LocalUserAccount(
            user_id=secrets.token_hex(8),
            email=cleaned_email,
            name=cleaned_name,
            password_hash=_derive_password_hash(password, salt),
            password_salt=salt,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        users.append(account)
        self._write_users(users)
        session = AuthSession(
            provider="local",
            email=account.email,
            name=account.name,
            connected=True,
            user_id=account.user_id,
        )
        if remember:
            self._write_profile(session)
        return session

    def authenticate(self, email: str, password: str, remember: bool = True) -> AuthSession:
        cleaned_email = _normalize_email(email)
        account = next((user for user in self._read_users() if user.email == cleaned_email), None)
        if account is None:
            raise InvalidCredentialsError("האימייל או הסיסמה אינם נכונים.")
        expected_hash = _derive_password_hash(password, account.password_salt)
        if not hmac.compare_digest(expected_hash, account.password_hash):
            raise InvalidCredentialsError("האימייל או הסיסמה אינם נכונים.")

        session = AuthSession(
            provider="local",
            email=account.email,
            name=account.name,
            connected=True,
            user_id=account.user_id,
        )
        if remember:
            self._write_profile(session)
        return session

    def load_session(self) -> AuthSession:
        payload = self._read_profile()
        if payload.get("provider") != "local":
            return AuthSession()
        email = _normalize_email(str(payload.get("email", "")))
        account = next((user for user in self._read_users() if user.email == email), None)
        if account is None:
            return AuthSession()
        return AuthSession(
            provider="local",
            email=account.email,
            name=account.name,
            connected=True,
            user_id=account.user_id,
        )

    def sign_out(self) -> None:
        payload = self._read_profile()
        if payload.get("provider") == "local" and self.profile_path.exists():
            self.profile_path.unlink()

    def _validate_registration(self, name: str, email: str, password: str) -> None:
        if not name:
            raise LocalAuthError("צריך להזין שם מלא.")
        if "@" not in email or "." not in email.split("@", 1)[-1]:
            raise LocalAuthError("צריך להזין כתובת אימייל תקינה.")
        if len(password) < 6:
            raise WeakPasswordError("הסיסמה צריכה לכלול לפחות 6 תווים.")

    def _write_profile(self, session: AuthSession) -> None:
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": session.provider,
            "email": session.email,
            "name": session.name,
            "picture": session.picture,
            "user_id": session.user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_profile(self) -> dict[str, object]:
        if not self.profile_path.exists():
            return {}
        try:
            return json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _read_users(self) -> list[LocalUserAccount]:
        if not self.users_path.exists():
            return []
        try:
            payload = json.loads(self.users_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        users: list[LocalUserAccount] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            users.append(
                LocalUserAccount(
                    user_id=str(item.get("user_id", "")).strip(),
                    email=_normalize_email(str(item.get("email", ""))),
                    name=" ".join(str(item.get("name", "")).strip().split()),
                    password_hash=str(item.get("password_hash", "")).strip(),
                    password_salt=str(item.get("password_salt", "")).strip(),
                    created_at=str(item.get("created_at", "")).strip(),
                )
            )
        return users

    def _write_users(self, users: list[LocalUserAccount]) -> None:
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "password_hash": user.password_hash,
                "password_salt": user.password_salt,
                "created_at": user.created_at,
            }
            for user in users
        ]
        self.users_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class GoogleAuthService:
    def __init__(
        self,
        profile_path: Path | None = None,
        token_path: Path | None = None,
        client_secret_path: Path | None = None,
    ) -> None:
        self.profile_path = profile_path or default_profile_path()
        self.token_path = token_path or self.profile_path.with_name("google_token.json")
        self._client_secret_path = client_secret_path

    def load_session(self) -> AuthSession:
        profile_data = self._read_profile()
        if profile_data.get("provider") == "google":
            if self.token_path.exists():
                try:
                    return self.refresh_session()
                except GoogleAuthError:
                    pass
            return self._session_from_profile(profile_data, connected=False)

        if self.token_path.exists():
            try:
                return self.refresh_session()
            except GoogleAuthError:
                pass
        return AuthSession()

    def has_client_configuration(self) -> bool:
        return self.locate_client_secret() is not None

    def locate_client_secret(self) -> Path | None:
        if self._client_secret_path:
            return self._client_secret_path if self._client_secret_path.exists() else None
        for path in self.client_secret_candidates():
            if path.exists():
                return path
        return None

    def client_secret_candidates(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        configured = os.environ.get(GOOGLE_CLIENT_SECRET_ENV, "").strip()
        if configured:
            candidates.append(Path(configured).expanduser())
        candidates.append(app_root() / "config" / "google_client_secret.json")
        candidates.append(self.profile_path.with_name("google_client_secret.json"))

        unique: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return tuple(unique)

    def configuration_message(self) -> str:
        candidates = "\n".join(f"- {path}" for path in self.client_secret_candidates())
        return (
            "כדי להפעיל התחברות עם Google צריך קובץ OAuth של Desktop App.\n"
            "הורידי את ה-JSON מ-Google Cloud Console ושמרי אותו באחד מהמיקומים האלה:\n"
            f"{candidates}\n\n"
            "השם שמוצג באפליקציה ייגזר מהאימייל של המשתמש."
        )

    def sign_in(self) -> AuthSession:
        client_secret = self.locate_client_secret()
        if client_secret is None:
            raise AuthConfigurationError(self.configuration_message())

        InstalledAppFlow = self._load_installed_app_flow()

        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=list(GOOGLE_SCOPES))
            credentials = flow.run_local_server(
                port=0,
                authorization_prompt_message="נפתח דפדפן כדי להשלים התחברות עם Google.",
                success_message="ההתחברות הושלמה. אפשר לחזור לאפליקציית Capital Gains.",
                open_browser=True,
            )
        except OSError as exc:
            raise GoogleAuthError(f"לא הצלחתי לפתוח את תהליך ההתחברות: {exc}") from exc
        except Exception as exc:  # pragma: no cover - library / browser boundary
            raise GoogleAuthError(f"התחברות Google נכשלה: {exc}") from exc

        self._ensure_parent_dirs()
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        profile = self._fetch_user_profile(credentials.token)
        session = self._session_from_userinfo(profile)
        self._write_profile(session, extra={"google_name": str(profile.get("name", "")).strip()})
        return AuthSession(
            provider=session.provider,
            email=session.email,
            name=session.name,
            picture=session.picture,
            connected=True,
            user_id=session.user_id,
        )

    def refresh_session(self) -> AuthSession:
        credentials = self._load_credentials()
        if credentials is None or not credentials.valid:
            return AuthSession()

        profile = self._fetch_user_profile(credentials.token)
        session = self._session_from_userinfo(profile)
        self._write_profile(session, extra={"google_name": str(profile.get("name", "")).strip()})
        return AuthSession(
            provider=session.provider,
            email=session.email,
            name=session.name,
            picture=session.picture,
            connected=True,
            user_id=session.user_id,
        )

    def sign_out(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()

        profile_data = self._read_profile()
        if profile_data.get("provider") == "google" and self.profile_path.exists():
            self.profile_path.unlink()

    def _load_credentials(self):
        if not self.token_path.exists():
            return None

        Credentials = self._load_google_credentials()
        Request = self._load_google_request()

        try:
            credentials = Credentials.from_authorized_user_file(str(self.token_path), list(GOOGLE_SCOPES))
        except Exception as exc:
            raise GoogleAuthError(f"לא הצלחתי לקרוא את טוקן ההתחברות השמור: {exc}") from exc

        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as exc:  # pragma: no cover - network boundary
                raise GoogleAuthError(f"לא הצלחתי לרענן את טוקן Google: {exc}") from exc
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    def _fetch_user_profile(self, access_token: str) -> dict[str, object]:
        request = UrlRequest(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:  # pragma: no cover - network boundary
            detail = exc.read().decode("utf-8", errors="replace")
            raise GoogleAuthError(f"Google החזיר שגיאה בפרטי המשתמש: {detail or exc.reason}") from exc
        except URLError as exc:  # pragma: no cover - network boundary
            raise GoogleAuthError(f"לא הצלחתי למשוך את פרטי המשתמש מ-Google: {exc.reason}") from exc
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - network boundary
            raise GoogleAuthError(f"תגובה לא תקינה מ-Google: {exc}") from exc

    def _session_from_userinfo(self, payload: dict[str, object]) -> AuthSession:
        email = str(payload.get("email", "")).strip()
        derived_name = display_name_from_email(email)
        fallback_name = str(payload.get("name", "")).strip()
        return AuthSession(
            provider="google",
            email=email,
            name=derived_name or fallback_name,
            picture=str(payload.get("picture", "")).strip(),
            connected=True,
            user_id=str(payload.get("sub", "")).strip(),
        )

    def _session_from_profile(self, payload: dict[str, object], connected: bool) -> AuthSession:
        return AuthSession(
            provider=str(payload.get("provider", "")).strip(),
            email=str(payload.get("email", "")).strip(),
            name=str(payload.get("name", "")).strip(),
            picture=str(payload.get("picture", "")).strip(),
            connected=connected,
            user_id=str(payload.get("user_id", "")).strip(),
        )

    def _write_profile(self, session: AuthSession, extra: dict[str, object] | None = None) -> None:
        self._ensure_parent_dirs()
        payload: dict[str, object] = {
            "provider": session.provider,
            "email": session.email,
            "name": session.name,
            "picture": session.picture,
            "user_id": session.user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            payload.update(extra)
        self.profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_profile(self) -> dict[str, object]:
        if not self.profile_path.exists():
            return {}
        try:
            return json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _ensure_parent_dirs(self) -> None:
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_installed_app_flow():
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:  # pragma: no cover - dependency boundary
            raise GoogleAuthError("חסר package בשם google-auth-oauthlib. הריצי התקנת requirements מחדש.") from exc
        return InstalledAppFlow

    @staticmethod
    def _load_google_credentials():
        try:
            from google.oauth2.credentials import Credentials
        except ImportError as exc:  # pragma: no cover - dependency boundary
            raise GoogleAuthError("חסר package בשם google-auth. הריצי התקנת requirements מחדש.") from exc
        return Credentials

    @staticmethod
    def _load_google_request():
        try:
            from google.auth.transport.requests import Request
        except ImportError as exc:  # pragma: no cover - dependency boundary
            raise GoogleAuthError("חסר package בשם requests או google-auth transport. הריצי התקנת requirements מחדש.") from exc
        return Request


class AuthService:
    def __init__(
        self,
        profile_path: Path | None = None,
        token_path: Path | None = None,
        client_secret_path: Path | None = None,
        users_path: Path | None = None,
    ) -> None:
        self.profile_path = profile_path or default_profile_path()
        self.google = GoogleAuthService(
            profile_path=self.profile_path,
            token_path=token_path,
            client_secret_path=client_secret_path,
        )
        self.local = LocalUserAuthService(profile_path=self.profile_path, users_path=users_path)

    def load_session(self) -> AuthSession:
        payload = self._read_profile()
        provider = str(payload.get("provider", "")).strip()
        if provider == "local":
            return self.local.load_session()
        return self.google.load_session()

    def has_google_configuration(self) -> bool:
        return self.google.has_client_configuration()

    def google_configuration_message(self) -> str:
        return self.google.configuration_message()

    def sign_in_with_google(self) -> AuthSession:
        return self.google.sign_in()

    def sign_in_local(self, email: str, password: str, remember: bool = True) -> AuthSession:
        return self.local.authenticate(email, password, remember=remember)

    def register_local_user(self, name: str, email: str, password: str, remember: bool = True) -> AuthSession:
        return self.local.register_user(name, email, password, remember=remember)

    def sign_out(self) -> None:
        self.google.sign_out()
        self.local.sign_out()

    def _read_profile(self) -> dict[str, object]:
        if not self.profile_path.exists():
            return {}
        try:
            return json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _derive_password_hash(password: str, salt: str) -> str:
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return base64.b64encode(derived).decode("ascii")
