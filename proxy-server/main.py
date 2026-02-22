import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Configuration ---

CONFIG_PATH = Path(__file__).parent / "config.json"
SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"

with open(CONFIG_PATH) as f:
    config = json.load(f)

OPENROUTER_API_KEY = config["openrouter_api_key"]
OPENROUTER_BASE_URL = config["openrouter_base_url"]
OPENROUTER_MODEL = config["openrouter_model"]
REQUEST_TIMEOUT = config.get("request_timeout_seconds", 15)
LOG_FILE = config.get("log_file", "server.log")
HOST = config.get("host", "0.0.0.0")
PORT = config.get("port", 8080)

# --- Logging ---

logger = logging.getLogger("translation-proxy")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(Path(__file__).parent / LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(stream_handler)

# --- Models ---


class ContextMessage(BaseModel):
    role: str  # "me" or "them"
    text: str


class TranslateRequest(BaseModel):
    text: str
    direction: str  # "incoming" or "outgoing"
    chat_id: str = ""
    context: list[ContextMessage] = Field(default_factory=list)


class TranslateResponse(BaseModel):
    translated_text: str
    original_text: str
    direction: str
    translation_failed: bool = False


# --- Translation Service ---


class TranslationService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self.stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "retries": 0,
            "fallbacks": 0,
            "total_response_time_ms": 0.0,
        }
        self.last_successful_translation: Optional[float] = None

    def _read_system_prompt(self) -> str:
        try:
            return SYSTEM_PROMPT_PATH.read_text().strip()
        except FileNotFoundError:
            logger.warning("system_prompt.txt not found, using default prompt")
            return (
                "You are a translator. Translate the given text accurately. "
                "Only output the translation, nothing else."
            )

    def _build_messages(
        self,
        text: str,
        direction: str,
        context: list[ContextMessage],
        system_prompt: str,
    ) -> list[dict]:
        messages = [{"role": "system", "content": system_prompt}]

        if context:
            context_text = "Here is the recent conversation for context (do NOT translate these, only use them to understand the conversation flow):\n\n"
            for msg in context:
                label = "Me" if msg.role == "me" else "Them"
                context_text += f"{label}: {msg.text}\n"
            context_text += "\n---\n\n"

            if direction == "outgoing":
                user_content = (
                    f"{context_text}"
                    f"Now translate the following message from English to German. "
                    f"Output ONLY the German translation, nothing else:\n\n{text}"
                )
            else:
                user_content = (
                    f"{context_text}"
                    f"Now translate the following message from German to English. "
                    f"Output ONLY the English translation, nothing else:\n\n{text}"
                )
        else:
            if direction == "outgoing":
                user_content = (
                    f"Translate the following message from English to German. "
                    f"Output ONLY the German translation, nothing else:\n\n{text}"
                )
            else:
                user_content = (
                    f"Translate the following message from German to English. "
                    f"Output ONLY the English translation, nothing else:\n\n{text}"
                )

        messages.append({"role": "user", "content": user_content})
        return messages

    async def _call_openrouter(self, messages: list[dict]) -> str:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://translategram.app",
            "X-Title": "TranslateGram",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
            "reasoning": {"effort": "none"},
        }

        response = await self.client.post(
            OPENROUTER_BASE_URL, headers=headers, json=payload
        )

        if response.status_code == 402:
            raise PaymentError(f"Payment required: {response.text}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "5")
            raise RateLimitError(
                f"Rate limited", retry_after=float(retry_after)
            )
        if response.status_code >= 400:
            raise OpenRouterError(
                f"HTTP {response.status_code}: {response.text}"
            )

        data = response.json()

        if "error" in data:
            error_code = data["error"].get("code", 0)
            if error_code == 402:
                raise PaymentError(f"Payment required: {data['error']}")
            if error_code == 429:
                raise RateLimitError(f"Rate limited: {data['error']}")
            raise OpenRouterError(f"API error: {data['error']}")

        choices = data.get("choices", [])
        if not choices:
            raise EmptyResponseError("No choices in response")

        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            raise EmptyResponseError("Empty content in response")

        return content

    async def translate(self, request: TranslateRequest) -> TranslateResponse:
        self.stats["total_requests"] += 1
        start_time = time.time()

        system_prompt = self._read_system_prompt()
        messages = self._build_messages(
            request.text, request.direction, request.context, system_prompt
        )

        translated_text = None
        translation_failed = False

        try:
            translated_text = await self._retry_translate(messages)
        except TranslationExhaustedError:
            logger.error(
                f"All retries exhausted for chat_id={request.chat_id} "
                f"direction={request.direction} text_len={len(request.text)}"
            )
            translated_text = request.text
            translation_failed = True
            self.stats["failed"] += 1
            self.stats["fallbacks"] += 1

        elapsed_ms = (time.time() - start_time) * 1000
        self.stats["total_response_time_ms"] += elapsed_ms

        if not translation_failed:
            self.stats["successful"] += 1
            self.last_successful_translation = time.time()

        logger.info(
            f"chat_id={request.chat_id} direction={request.direction} "
            f"text_len={len(request.text)} response_time_ms={elapsed_ms:.0f} "
            f"failed={translation_failed}"
        )

        return TranslateResponse(
            translated_text=translated_text,
            original_text=request.text,
            direction=request.direction,
            translation_failed=translation_failed,
        )

    async def _retry_translate(self, messages: list[dict]) -> str:
        last_exception = None

        # Attempt 1: initial try
        # Attempts 2-6: retries with appropriate strategy per error type
        max_total_attempts = 6  # 1 initial + 5 retries (worst case: empty response)

        empty_delays = [1, 2, 4, 8, 16]
        payment_delays = [5, 5, 5]
        timeout_delays = [0, 0, 0]

        empty_retries = 0
        payment_retries = 0
        timeout_retries = 0
        rate_limit_retries = 0

        for attempt in range(max_total_attempts):
            try:
                return await self._call_openrouter(messages)
            except EmptyResponseError as e:
                last_exception = e
                if empty_retries >= len(empty_delays):
                    break
                delay = empty_delays[empty_retries]
                empty_retries += 1
                self.stats["retries"] += 1
                logger.warning(
                    f"Empty response, retry {empty_retries}/5 after {delay}s"
                )
                await asyncio.sleep(delay)
            except PaymentError as e:
                last_exception = e
                if payment_retries >= len(payment_delays):
                    break
                delay = payment_delays[payment_retries]
                payment_retries += 1
                self.stats["retries"] += 1
                logger.warning(
                    f"Payment error, retry {payment_retries}/3 after {delay}s"
                )
                await asyncio.sleep(delay)
            except RateLimitError as e:
                last_exception = e
                if rate_limit_retries >= 3:
                    break
                delay = e.retry_after
                rate_limit_retries += 1
                self.stats["retries"] += 1
                logger.warning(
                    f"Rate limited, retry {rate_limit_retries}/3 after {delay}s"
                )
                await asyncio.sleep(delay)
            except (httpx.TimeoutException, httpx.ReadError, httpx.ConnectError) as e:
                last_exception = e
                if timeout_retries >= len(timeout_delays):
                    break
                timeout_retries += 1
                self.stats["retries"] += 1
                logger.warning(
                    f"Connection/timeout error ({type(e).__name__}), "
                    f"retry {timeout_retries}/3"
                )
            except OpenRouterError as e:
                last_exception = e
                logger.error(f"OpenRouter error (no retry): {type(e).__name__}: {e}")
                break
            except Exception as e:
                last_exception = e
                logger.error(
                    f"Unexpected error (no retry): {type(e).__name__}: {repr(e)}"
                )
                break

        raise TranslationExhaustedError(
            f"All retries exhausted. Last error: {last_exception}"
        )


# --- Custom Exceptions ---


class OpenRouterError(Exception):
    pass


class EmptyResponseError(OpenRouterError):
    pass


class PaymentError(OpenRouterError):
    pass


class RateLimitError(OpenRouterError):
    def __init__(self, message: str, retry_after: float = 5.0):
        super().__init__(message)
        self.retry_after = retry_after


class TranslationExhaustedError(Exception):
    pass


# --- FastAPI App ---

SERVER_START_TIME = time.time()
translation_service = TranslationService()

app = FastAPI(title="TranslateGram Proxy", version="1.0.0")


@app.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest):
    if not request.text.strip():
        return TranslateResponse(
            translated_text=request.text,
            original_text=request.text,
            direction=request.direction,
            translation_failed=False,
        )
    return await translation_service.translate(request)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - SERVER_START_TIME, 1),
        "last_successful_translation": translation_service.last_successful_translation,
    }


@app.get("/stats")
async def stats():
    s = translation_service.stats
    total = s["total_requests"]
    avg_ms = (s["total_response_time_ms"] / total) if total > 0 else 0
    return {
        "total_requests": total,
        "successful": s["successful"],
        "failed": s["failed"],
        "retries": s["retries"],
        "fallbacks": s["fallbacks"],
        "success_rate": round(s["successful"] / total, 4) if total > 0 else 0,
        "avg_response_time_ms": round(avg_ms, 1),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
