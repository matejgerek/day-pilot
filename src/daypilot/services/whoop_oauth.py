from __future__ import annotations

import base64
import json
import secrets
import string
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from daypilot.services.config import WhoopConfig

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
DEFAULT_SCOPE = (
    "offline read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement"
)


class WhoopOAuthError(RuntimeError):
    """Raised when WHOOP OAuth flow fails."""


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    scope: str | None
    token_type: str | None


@dataclass
class _CallbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None


class _CallbackServer(HTTPServer):
    def __init__(self, server_address: tuple[str, int], redirect_path: str) -> None:
        super().__init__(server_address, _CallbackHandler)
        self.redirect_path = redirect_path
        self.result = _CallbackResult()
        self.event = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        server = self.server
        if not isinstance(server, _CallbackServer):
            self.send_error(500, "Invalid callback server")
            return

        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != server.redirect_path:
            self.send_error(404, "Not Found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        server.result.code = _first_param(params.get("code"))
        server.result.state = _first_param(params.get("state"))
        server.result.error = _first_param(params.get("error"))
        server.event.set()

        message = "WHOOP connection received. You can return to the CLI and close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


class WhoopOAuthService:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_host: str = "127.0.0.1",
        redirect_port: int = 8765,
        redirect_path: str = "/callback",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_host = redirect_host
        self._redirect_port = redirect_port
        self._redirect_path = redirect_path

    @property
    def redirect_uri(self) -> str:
        return f"http://{self._redirect_host}:{self._redirect_port}{self._redirect_path}"

    def connect(self, scope: str | None = None, timeout_seconds: int = 300) -> WhoopConfig:
        state = _generate_state()
        scope_value = scope or DEFAULT_SCOPE

        try:
            server = _CallbackServer(
                (self._redirect_host, self._redirect_port),
                self._redirect_path,
            )
        except OSError as exc:
            raise WhoopOAuthError("Could not start local callback server.") from exc

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        auth_url = self._build_auth_url(scope_value, state)
        webbrowser.open(auth_url)

        if not server.event.wait(timeout_seconds):
            server.shutdown()
            thread.join(timeout=2)
            raise WhoopOAuthError("Timed out waiting for WHOOP authorization.")

        server.shutdown()
        thread.join(timeout=2)

        if server.result.error:
            raise WhoopOAuthError(f"Authorization error: {server.result.error}")
        if server.result.state != state:
            raise WhoopOAuthError("Authorization state mismatch.")
        if not server.result.code:
            raise WhoopOAuthError("Authorization code missing.")

        tokens = self._exchange_code(server.result.code, scope_value)
        now = datetime.now(timezone.utc)
        expires_at = None
        if tokens.expires_in:
            expires_at = now + timedelta(seconds=tokens.expires_in)

        return WhoopConfig(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            scope=tokens.scope,
            token_type=tokens.token_type,
            expires_at=expires_at,
            connected_at=now,
            last_sync_at=None,
        )

    def _build_auth_url(self, scope: str, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "state": state,
        }
        return f"{WHOOP_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _exchange_code(self, code: str, scope: str) -> OAuthTokens:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        errors: list[str] = []
        for mode in ("json", "form", "form_basic"):
            try:
                payload_data = self._post_token_request(payload, mode=mode)
                break
            except WhoopOAuthError as exc:
                errors.append(f"{mode}: {exc}")
        else:
            raise WhoopOAuthError("Token exchange failed. " + " | ".join(errors))

        access_token = str(payload_data.get("access_token", "")).strip()
        if not access_token:
            raise WhoopOAuthError(f"Token exchange response missing access_token: {payload_data}")

        return OAuthTokens(
            access_token=access_token,
            refresh_token=_optional_str(payload_data.get("refresh_token")),
            expires_in=_optional_int(payload_data.get("expires_in")),
            scope=_optional_str(payload_data.get("scope")),
            token_type=_optional_str(payload_data.get("token_type")),
        )

    def _post_token_request(self, payload: dict[str, Any], mode: str) -> dict[str, Any]:
        if mode == "json":
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "daypilot/0.1.0",
            }
        elif mode == "form":
            data = urllib.parse.urlencode(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "daypilot/0.1.0",
            }
        elif mode == "form_basic":
            basic_payload = dict(payload)
            basic_payload.pop("client_secret", None)
            data = urllib.parse.urlencode(basic_payload).encode("utf-8")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Authorization": _basic_auth_header(self._client_id, self._client_secret),
                "User-Agent": "daypilot/0.1.0",
            }
        else:
            raise WhoopOAuthError(f"Unsupported token request mode: {mode}")

        request = urllib.request.Request(
            WHOOP_TOKEN_URL,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail_bytes = exc.read()
            detail = detail_bytes.decode("utf-8", errors="replace").strip()
            hint = ""
            if exc.code == 401:
                hint = " Check WHOOP_CLIENT_ID/WHOOP_CLIENT_SECRET."
            if "1010" in detail:
                hint = (
                    " Check WHOOP dashboard redirect URL matches exactly "
                    f"({self.redirect_uri}) and your client secret is correct."
                )
            raise WhoopOAuthError(f"HTTP {exc.code}: {detail}{hint}") from exc
        except urllib.error.URLError as exc:
            raise WhoopOAuthError("Network error while exchanging token.") from exc

        try:
            payload_data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WhoopOAuthError(
                "Token exchange returned invalid JSON: " + raw.decode("utf-8", errors="replace")
            ) from exc

        if not isinstance(payload_data, dict):
            raise WhoopOAuthError(f"Token exchange returned unexpected payload: {payload_data}")
        return payload_data


def _first_param(values: list[str] | None) -> str | None:
    if not values:
        return None
    return values[0]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _generate_state() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"
