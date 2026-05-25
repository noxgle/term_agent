import json
import os
import time
from typing import Optional, Dict, Any

import requests


class OpenAIDeviceOAuthManager:
    """Handles OAuth Device Code flow token lifecycle for OpenAI."""

    def __init__(self, basedir: str, logger=None):
        self.basedir = basedir
        self.logger = logger
        self.auth_mode = os.getenv("OPENAI_AUTH_MODE", "api_key").strip().lower()
        self.client_id = os.getenv("OPENAI_OAUTH_CLIENT_ID", "app_EMoamEEZ73f0CkXaXp7hrann").strip()
        self.scope = os.getenv("OPENAI_OAUTH_SCOPE", "")
        self.audience = os.getenv("OPENAI_OAUTH_AUDIENCE", "")
        self.base_url = os.getenv("OPENAI_OAUTH_BASE_URL", "https://auth.openai.com").strip().rstrip("/")
        self.device_code_url = os.getenv(
            "OPENAI_OAUTH_DEVICE_CODE_URL",
            f"{self.base_url}/api/accounts/deviceauth/usercode",
        ).strip()
        self.device_token_url = os.getenv(
            "OPENAI_OAUTH_DEVICE_TOKEN_URL",
            f"{self.base_url}/api/accounts/deviceauth/token",
        ).strip()
        self.token_url = os.getenv(
            "OPENAI_OAUTH_TOKEN_URL",
            f"{self.base_url}/oauth/token",
        ).strip()
        self.device_verify_url = os.getenv(
            "OPENAI_OAUTH_DEVICE_VERIFY_URL",
            f"{self.base_url}/codex/device",
        ).strip()
        self.device_callback_url = os.getenv(
            "OPENAI_OAUTH_DEVICE_CALLBACK_URL",
            f"{self.base_url}/deviceauth/callback",
        ).strip()
        token_file_raw = os.getenv("OPENAI_OAUTH_TOKEN_FILE", ".auth/openai_token.json").strip()
        self.token_file = token_file_raw if os.path.isabs(token_file_raw) else os.path.join(self.basedir, token_file_raw)

    def _log(self, level: str, message: str):
        if self.logger:
            log_fn = getattr(self.logger, level, None)
            if callable(log_fn):
                log_fn(message)

    def is_enabled(self) -> bool:
        return self.auth_mode == "oauth"

    def _token_exists(self) -> bool:
        return os.path.isfile(self.token_file)

    def _load_token(self) -> Optional[Dict[str, Any]]:
        if not self._token_exists():
            return None
        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self._log("warning", f"Failed to load OAuth token file: {e}")
            return None

    def _save_token(self, token_data: Dict[str, Any]) -> None:
        parent = os.path.dirname(self.token_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        token_copy = dict(token_data)
        if "expires_in" in token_copy:
            try:
                token_copy["expires_at"] = int(time.time()) + int(token_copy["expires_in"]) - 30
            except Exception:
                token_copy["expires_at"] = int(time.time()) + 3500
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(token_copy, f, indent=2)
        try:
            os.chmod(self.token_file, 0o600)
        except Exception:
            pass

    def logout(self) -> bool:
        if self._token_exists():
            os.remove(self.token_file)
            self._log("info", "OpenAI OAuth token removed.")
            return True
        return False

    def _is_access_token_valid(self, token_data: Dict[str, Any]) -> bool:
        access_token = token_data.get("access_token")
        expires_at = token_data.get("expires_at")
        if not access_token:
            return False
        if not expires_at:
            return True
        return int(time.time()) < int(expires_at)

    def _refresh_token(self, refresh_token: str) -> Optional[str]:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if self.client_id:
            payload["client_id"] = self.client_id
        resp = requests.post(self.token_url, data=payload, timeout=30)
        if resp.status_code >= 400:
            self._log("warning", f"OpenAI OAuth refresh failed: HTTP {resp.status_code} {resp.text[:300]}")
            return None
        token_data = resp.json()
        if "access_token" not in token_data:
            self._log("warning", f"OpenAI OAuth refresh returned no access_token: {token_data}")
            return None
        if "refresh_token" not in token_data:
            token_data["refresh_token"] = refresh_token
        self._save_token(token_data)
        return token_data.get("access_token")

    def get_valid_access_token(self, interactive: bool = False, console=None) -> Optional[str]:
        if not self.is_enabled():
            return None

        token_data = self._load_token()
        if token_data and self._is_access_token_valid(token_data):
            return token_data.get("access_token")

        if token_data and token_data.get("refresh_token"):
            refreshed = self._refresh_token(token_data["refresh_token"])
            if refreshed:
                return refreshed

        if interactive:
            return self.login_device_flow(console=console)
        return None

    def _print(self, message: str, console=None):
        if console:
            console.print(message)
        else:
            print(message)

    def login_device_flow(self, console=None) -> Optional[str]:
        if not self.is_enabled():
            self._print("OpenAI OAuth is disabled (OPENAI_AUTH_MODE != oauth).", console=console)
            return None

        payload = {}
        if self.client_id:
            payload["client_id"] = self.client_id
        if self.scope:
            payload["scope"] = self.scope
        if self.audience:
            payload["audience"] = self.audience

        try:
            device_resp = requests.post(
                self.device_code_url,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=30,
            )
            device_resp.raise_for_status()
            data = device_resp.json()
        except Exception as e:
            self._print(f"OpenAI OAuth device flow init failed: {e}", console=console)
            return None

        device_auth_id = data.get("device_auth_id")
        user_code = data.get("user_code") or data.get("usercode")
        verification_uri = self.device_verify_url
        interval = int(data.get("interval", 5))
        expires_in = int(data.get("expires_in", 600))

        if not device_auth_id or not verification_uri or not user_code:
            self._print(f"Invalid OAuth device response: {data}", console=console)
            return None

        self._print("\nOpenAI OAuth login required:", console=console)
        self._print(f"1) Open: {verification_uri}", console=console)
        self._print(f"2) Enter code: {user_code}\n", console=console)

        deadline = time.time() + expires_in
        while time.time() < deadline:
            token_payload = {
                "device_auth_id": device_auth_id,
                "user_code": user_code,
            }
            try:
                token_resp = requests.post(
                    self.device_token_url,
                    json=token_payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    timeout=30,
                )
                if token_resp.status_code == 200:
                    code_data = token_resp.json()
                    authorization_code = code_data.get("authorization_code")
                    code_verifier = code_data.get("code_verifier")
                    if not authorization_code or not code_verifier:
                        self._print(f"OAuth device token response missing fields: {code_data}", console=console)
                        return None

                    form_payload = {
                        "grant_type": "authorization_code",
                        "code": authorization_code,
                        "code_verifier": code_verifier,
                        "redirect_uri": self.device_callback_url,
                    }
                    if self.client_id:
                        form_payload["client_id"] = self.client_id
                    final_resp = requests.post(self.token_url, data=form_payload, timeout=30)
                    if final_resp.status_code >= 400:
                        self._print(
                            f"OAuth code exchange failed: HTTP {final_resp.status_code} {final_resp.text[:300]}",
                            console=console,
                        )
                        return None
                    token_data = final_resp.json()
                    if token_data.get("access_token"):
                        self._save_token(token_data)
                        self._print("OpenAI OAuth login successful.", console=console)
                        return token_data.get("access_token")
                else:
                    if token_resp.status_code in (403, 404):
                        pass
                    elif token_resp.status_code == 429:
                        interval += 2
                    else:
                        self._print(
                            f"OAuth token polling failed: HTTP {token_resp.status_code} {token_resp.text[:300]}",
                            console=console,
                        )
                        return None
            except Exception as e:
                self._log("warning", f"OAuth token polling error: {e}")

            time.sleep(interval)

        self._print("OAuth login timed out. Try again.", console=console)
        return None
