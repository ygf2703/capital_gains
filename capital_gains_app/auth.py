from __future__ import annotations

import json
import os
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


class GoogleAuthError(RuntimeError):
    """Raised when the local Google sign-in flow fails."""


class AuthConfigurationError(GoogleAuthError):
    """Raised when the app is missing Google OAuth client configuration."""


@dataclass(frozen=True, slots=True)
class AuthSession:
    provider: str = ""
    email: str = ""
    name: str = ""
    picture: str = ""
    connected: bool = False

    @property
    def identity(self) -> UserIdentity:
        return UserIdentity(email=self.email, name=self.name)


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
        )

    def _session_from_profile(self, payload: dict[str, object], connected: bool) -> AuthSession:
        return AuthSession(
            provider=str(payload.get("provider", "")).strip(),
            email=str(payload.get("email", "")).strip(),
            name=str(payload.get("name", "")).strip(),
            picture=str(payload.get("picture", "")).strip(),
            connected=connected,
        )

    def _write_profile(self, session: AuthSession, extra: dict[str, object] | None = None) -> None:
        self._ensure_parent_dirs()
        payload: dict[str, object] = {
            "provider": session.provider,
            "email": session.email,
            "name": session.name,
            "picture": session.picture,
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
