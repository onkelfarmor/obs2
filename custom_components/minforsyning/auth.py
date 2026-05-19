"""Authentication handler for MinForsyning via KMD Easy Energy OIDC/PKCE."""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import urllib.parse
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Optional

import aiohttp

from .const import (
    APP_ID,
    AUTHORIZE_PATH,
    CLIENT_ID,
    IDENTITY_BASE_URL,
    LOGIN_URL,
    REDIRECT_URI,
    SCOPE,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)


class _FormParser(HTMLParser):
    """Extract form fields and CSRF token from an HTML login page."""

    def __init__(self) -> None:
        super().__init__()
        self.csrf_token: Optional[str] = None
        self.form_action: Optional[str] = None
        self.hidden_fields: dict[str, str] = {}
        self._in_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        d = dict(attrs)
        if tag == "form":
            self._in_form = True
            self.form_action = d.get("action")
        if tag == "input" and self._in_form:
            name = d.get("name", "")
            value = d.get("value", "") or ""
            if name == "__RequestVerificationToken":
                self.csrf_token = value
            elif d.get("type") == "hidden" and name:
                self.hidden_fields[name] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._in_form = False


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class MinForsyningAuth:
    """Manages the PKCE OAuth2 login flow and token lifecycle."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        utility: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._utility = utility
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # PKCE helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_verifier() -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()

    @staticmethod
    def _make_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def _build_login_url(self, code_challenge: str, state: str, nonce: str) -> str:
        oidc_params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "nonce": nonce,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "utility": self._utility,
            "login_type": "mf",
            "post_logout_redirect_uri": REDIRECT_URI,
            "app": APP_ID,
        }
        return_url = AUTHORIZE_PATH + "?" + urllib.parse.urlencode(oidc_params)
        return LOGIN_URL + "?" + urllib.parse.urlencode({"ReturnUrl": return_url})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        """Perform the full PKCE login flow and store tokens."""
        verifier = self._make_verifier()
        challenge = self._make_challenge(verifier)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        login_url = self._build_login_url(challenge, state, nonce)

        # 1. Load login page → get CSRF token
        async with self._session.get(login_url) as resp:
            if resp.status != 200:
                raise AuthenticationError(f"Login page returned {resp.status}")
            html = await resp.text()
            effective_url = str(resp.url)

        parser = _FormParser()
        parser.feed(html)

        if not parser.csrf_token:
            raise AuthenticationError(
                "Could not find __RequestVerificationToken on login page. "
                "The login page structure may have changed."
            )

        # 2. POST credentials
        post_url = parser.form_action or effective_url
        if not post_url.startswith("http"):
            base = f"{urllib.parse.urlparse(effective_url).scheme}://{urllib.parse.urlparse(effective_url).netloc}"
            post_url = base + post_url

        form_data: dict[str, str] = {
            **parser.hidden_fields,
            "__RequestVerificationToken": parser.csrf_token,
            "Input.Email": self._email,
            "Input.Password": self._password,
            "Input.RememberMe": "false",
        }

        auth_code = await self._post_login_and_capture_code(post_url, form_data, state)

        # 3. Exchange code → tokens
        await self._exchange_code(auth_code, verifier)
        _LOGGER.debug("MinForsyning authentication successful")

    async def get_valid_token(self) -> str:
        """Return a valid access token, refreshing automatically if needed."""
        if not self.access_token:
            raise AuthenticationError("Not authenticated – call authenticate() first")

        if self._expires_at and datetime.now() >= self._expires_at:
            if self.refresh_token:
                await self._do_refresh()
            else:
                raise AuthenticationError("Access token expired and no refresh token available")

        return self.access_token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post_login_and_capture_code(
        self, post_url: str, form_data: dict[str, str], expected_state: str
    ) -> str:
        """POST the login form, follow redirects, and return the auth code."""
        async with self._session.post(post_url, data=form_data, allow_redirects=False) as resp:
            status = resp.status
            location = resp.headers.get("Location", "")

            if status == 200:
                body = await resp.text()
                lower = body.lower()
                if any(kw in lower for kw in ("invalid", "incorrect", "fejl", "wrong", "forkert")):
                    raise AuthenticationError("Invalid email or password")
                raise AuthenticationError(
                    f"Login did not redirect (status 200). "
                    "Check credentials or whether 2FA/email-link login is required."
                )
            if status not in (301, 302, 303, 307, 308):
                raise AuthenticationError(f"Unexpected response after login POST: {status}")

        return await self._follow_redirects_for_code(location, post_url, expected_state)

    async def _follow_redirects_for_code(
        self, location: str, base_url: str, expected_state: str, max_hops: int = 15
    ) -> str:
        current_base = base_url
        for _ in range(max_hops):
            # Resolve relative URLs
            if not location.startswith("http"):
                parsed_base = urllib.parse.urlparse(current_base)
                location = f"{parsed_base.scheme}://{parsed_base.netloc}{location}"

            parsed = urllib.parse.urlparse(location)
            qs = urllib.parse.parse_qs(parsed.query)

            if "code" in qs:
                code = qs["code"][0]
                _LOGGER.debug("Captured auth code from redirect to %s", parsed.netloc)
                return code

            if "error" in qs:
                raise AuthenticationError(
                    f"OAuth error: {qs.get('error', ['?'])[0]} – {qs.get('error_description', [''])[0]}"
                )

            async with self._session.get(location, allow_redirects=False) as resp:
                current_base = str(resp.url)
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                elif resp.status == 200:
                    final_qs = urllib.parse.parse_qs(urllib.parse.urlparse(current_base).query)
                    if "code" in final_qs:
                        return final_qs["code"][0]
                    raise AuthenticationError(
                        "Auth flow ended at a 200 page without an authorization code"
                    )
                else:
                    raise AuthenticationError(f"Redirect error {resp.status} at {current_base}")

        raise AuthenticationError("Too many redirects in auth flow")

    async def _exchange_code(self, code: str, verifier: str) -> None:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": verifier,
        }
        async with self._session.post(TOKEN_URL, data=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(f"Token exchange failed ({resp.status}): {body}")
            data = await resp.json()
        self._store_tokens(data)

    async def _do_refresh(self) -> None:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": CLIENT_ID,
        }
        async with self._session.post(TOKEN_URL, data=payload) as resp:
            if resp.status != 200:
                raise AuthenticationError("Token refresh failed – will re-authenticate on next update")
            data = await resp.json()
        self._store_tokens(data)
        _LOGGER.debug("MinForsyning token refreshed")

    def _store_tokens(self, data: dict) -> None:
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        expires_in = int(data.get("expires_in", 3600))
        # Subtract 60 s buffer so we refresh before actual expiry
        self._expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

    # ------------------------------------------------------------------
    # Serialisation (stored in config entry data)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expires": self._expires_at.isoformat() if self._expires_at else None,
        }

    @classmethod
    def from_dict(
        cls,
        session: aiohttp.ClientSession,
        stored: dict,
        email: str,
        password: str,
        utility: str,
    ) -> "MinForsyningAuth":
        obj = cls(session, email, password, utility)
        obj.access_token = stored.get("access_token")
        obj.refresh_token = stored.get("refresh_token")
        exp = stored.get("token_expires")
        obj._expires_at = datetime.fromisoformat(exp) if exp else None
        return obj
