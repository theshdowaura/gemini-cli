"""
OAuth login helper replicating Gemini CLI authentication.

This script opens a browser to authenticate with Google and stores the
resulting credentials in ``~/.gemini/oauth_creds.json``.
"""

# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0

import http.server
import json
import os
import secrets
import socket
import threading
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

OAUTH_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
)
OAUTH_CLIENT_SECRET = "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"
OAUTH_SCOPE = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"
SIGN_IN_SUCCESS_URL = (
    "https://developers.google.com/gemini-code-assist/auth_success_gemini"
)
SIGN_IN_FAILURE_URL = (
    "https://developers.google.com/gemini-code-assist/auth_failure_gemini"
)
GEMINI_DIR = ".gemini"
CREDENTIAL_FILENAME = "oauth_creds.json"


def _credential_path() -> str:
    return os.path.join(os.path.expanduser("~"), GEMINI_DIR, CREDENTIAL_FILENAME)


def _cache_credentials(creds: Credentials) -> None:
    path = _credential_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
                "token_uri": TOKEN_URI,
                "scopes": OAUTH_SCOPE,
            },
            f,
            indent=2,
        )


def _load_cached_credentials() -> Credentials | None:
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", _credential_path())
    try:
        with open(path, "r") as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_uri=TOKEN_URI,
            client_id=OAUTH_CLIENT_ID,
            client_secret=OAUTH_CLIENT_SECRET,
            scopes=OAUTH_SCOPE,
        )
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        r = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": creds.token},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        return creds
    except Exception:
        return None


def _available_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _auth_with_web() -> Credentials:
    port = _available_port()
    redirect_uri = f"http://localhost:{port}/oauth2callback"
    state = secrets.token_hex(32)
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "offline",
        "scope": " ".join(OAUTH_SCOPE),
        "state": state,
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    creds_container: dict[str, Credentials] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path != "/oauth2callback":
                self.send_response(301)
                self.send_header("Location", SIGN_IN_FAILURE_URL)
                self.end_headers()
                return
            query = parse_qs(parsed.query)
            if "error" in query:
                self.send_response(301)
                self.send_header("Location", SIGN_IN_FAILURE_URL)
                self.end_headers()
                return
            if query.get("state", [""])[0] != state:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"State mismatch. Possible CSRF attack")
                return
            code = query.get("code", [None])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code found in request")
                return
            resp = requests.post(
                TOKEN_URI,
                data={
                    "code": code,
                    "client_id": OAUTH_CLIENT_ID,
                    "client_secret": OAUTH_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            creds = Credentials(
                token=data.get("access_token"),
                refresh_token=data.get("refresh_token"),
                token_uri=TOKEN_URI,
                client_id=OAUTH_CLIENT_ID,
                client_secret=OAUTH_CLIENT_SECRET,
                scopes=OAUTH_SCOPE,
            )
            _cache_credentials(creds)
            creds_container["creds"] = creds
            self.send_response(301)
            self.send_header("Location", SIGN_IN_SUCCESS_URL)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: D401
            return

    server = http.server.HTTPServer(("", port), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print("\n\nCode Assist login required.")
    print("Attempting to open authentication page in your browser.")
    print(f"Otherwise navigate to:\n\n{auth_url}\n")
    webbrowser.open(auth_url)
    while "creds" not in creds_container:
        thread.join(0.1)
    server.shutdown()
    thread.join()
    return creds_container["creds"]


def get_oauth_credentials() -> Credentials:
    creds = _load_cached_credentials()
    if creds:
        return creds
    return _auth_with_web()


def clear_cached_credentials() -> None:
    try:
        os.remove(_credential_path())
    except OSError:
        pass


if __name__ == "__main__":
    credentials = get_oauth_credentials()
    print("Access token:", credentials.token)
