from __future__ import annotations
import os
from typing import Any
import requests
from services.telegram_control import TelegramControlPlane, TelegramResponse
from quant.models import DataStatus

class TelegramTransport:
    def __init__(self, token: str, *, timeout_seconds: float = 15.0):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN_REQUIRED")
        self.base = "https://api.telegram.org/bot" + token
        self.timeout_seconds = timeout_seconds

    def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        params = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(self.base + "/getUpdates", params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError("TELEGRAM_GET_UPDATES_FAILED")
        return list(payload.get("result") or [])

    def send(self, chat_id: str, response: TelegramResponse) -> None:
        payload: dict[str, Any] = {"chat_id": str(chat_id), "text": response.text, "disable_web_page_preview": True}
        if response.buttons:
            payload["reply_markup"] = {"inline_keyboard": [
                [{"text": text, "callback_data": data} for text, data in row]
                for row in response.buttons
            ]}
        result = requests.post(self.base + "/sendMessage", json=payload, timeout=self.timeout_seconds)
        result.raise_for_status()
        data = result.json()
        if not data.get("ok"):
            raise RuntimeError("TELEGRAM_SEND_FAILED")

    def answer_callback(self, callback_id: str) -> None:
        result = requests.post(
            self.base + "/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=self.timeout_seconds,
        )
        result.raise_for_status()

class MarketStateHTTPClient:
    def __init__(self, base_url: str, *, token: str | None = None, timeout_seconds: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def fetch(self, symbol: str) -> dict[str, Any] | None:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        response = requests.get(
            self.base_url + "/market/" + symbol.upper(),
            headers=headers,
            timeout=self.timeout_seconds,
        )
        if response.status_code == 503:
            return None
        response.raise_for_status()
        return response.json()

def _state_from_payload(payload: dict[str, Any] | None):
    if not payload:
        return None
    state = (payload.get("data") or {}).get("market_state") or {}
    class State:
        pass
    out = State()
    for key, value in state.items():
        setattr(out, key, value)
    out.data_status = DataStatus(state.get("data_status", "UNAVAILABLE"))
    return out

class TelegramPollingWorker:
    def __init__(self, control: TelegramControlPlane, transport: TelegramTransport, market_client: MarketStateHTTPClient | None = None, *, symbol: str = "GC"):
        self.control = control
        self.transport = transport
        self.market_client = market_client
        self.symbol = symbol
        self.offset: int | None = None

    def process_update(self, update: dict[str, Any]) -> bool:
        self.offset = int(update["update_id"]) + 1
        callback = update.get("callback_query")
        if callback:
            message = callback.get("message") or {}
            sender = callback.get("from") or {}
            chat = message.get("chat") or {}
            command = "/" + str(callback.get("data") or "").strip().lstrip("/")
            response = self.control.handle(
                user_id=str(sender.get("id", "")),
                chat_id=str(chat.get("id", "")),
                command=command,
                market_state=self._state(),
            )
            self.transport.send(str(chat.get("id", "")), response)
            callback_id = callback.get("id")
            if callback_id:
                self.transport.answer_callback(str(callback_id))
            return True

        message = update.get("message") or {}
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        text = str(message.get("text") or "").strip()
        if not text.startswith("/"):
            return False
        command = text.split()[0].split("@")[0]
        response = self.control.handle(
            user_id=str(sender.get("id", "")),
            chat_id=str(chat.get("id", "")),
            command=command,
            market_state=self._state(),
        )
        self.transport.send(str(chat.get("id", "")), response)
        return True

    def run_once(self) -> int:
        updates = self.transport.get_updates(self.offset)
        handled = 0
        for update in updates:
            if self.process_update(update):
                handled += 1
        return handled

    def _state(self):
        if self.market_client is None:
            return None
        try:
            return _state_from_payload(self.market_client.fetch(self.symbol))
        except Exception:
            return None

def build_worker_from_env(control: TelegramControlPlane) -> TelegramPollingWorker:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    base_url = os.environ.get("CANONICAL_MARKET_STATE_URL", "")
    market = (
        MarketStateHTTPClient(base_url, token=os.environ.get("CANONICAL_API_TOKEN"))
        if base_url else None
    )
    return TelegramPollingWorker(
        control,
        TelegramTransport(token),
        market,
        symbol=os.environ.get("CANONICAL_MARKET_STATE_SYMBOL", "GC"),
    )
