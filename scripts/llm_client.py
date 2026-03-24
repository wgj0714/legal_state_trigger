"""LLM API 클라이언트 (Google Gemini).

Google Gemini API를 호출하고 JSON 응답을 파싱하는 래퍼.
configs/app_config.yaml의 설정에 따라 동작한다.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types


# ─── 설정 로드 ───
CONFIG_PATH = Path(__file__).parent.parent / "configs" / "app_config.yaml"


def load_config() -> dict:
    """app_config.yaml 로드."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt(prompt_name: str) -> str:
    """prompts/ 디렉토리에서 프롬프트 파일 로드."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompts_dir / prompt_name
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


class LLMClient:
    """Google Gemini API 호출 래퍼."""

    def __init__(self, config: dict | None = None):
        if config is None:
            config = load_config()

        llm_cfg = config["llm"]
        self.model = llm_cfg["model_name"]
        self.temperature = llm_cfg.get("temperature", 0.1)
        self.max_retries = llm_cfg.get("max_retries", 3)

        # .env에서 API 키 로드
        self._load_env()

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 GOOGLE_API_KEY를 설정하세요."
            )

        self.client = genai.Client(api_key=api_key)

    def _load_env(self):
        """프로젝트 루트의 .env 파일에서 환경변수 로드."""
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        os.environ.setdefault(key.strip(), value.strip())

    def call(self, system_prompt: str, user_message: str) -> str:
        """Gemini에 메시지를 보내고 응답 텍스트를 반환."""
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=self.temperature,
                        response_mime_type="application/json",
                    ),
                )
                return response.text
            except Exception as e:
                print(f"  [재시도 {attempt + 1}/{self.max_retries}] 오류: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def call_json(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        """Gemini를 호출하고 응답을 JSON dict로 파싱하여 반환."""
        raw = self.call(system_prompt, user_message)
        return parse_json_response(raw)


def parse_json_response(text: str) -> dict[str, Any]:
    """LLM 응답에서 JSON을 추출하여 파싱.

    코드블록(```json ... ```) 안에 있을 수 있으므로 추출 처리.
    """
    # ```json ... ``` 블록에서 추출 시도
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        text = match.group(1)

    # 앞뒤 공백 제거 후 파싱
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [JSON 파싱 실패] {e}")
        print(f"  [원문 일부] {text[:200]}...")
        raise
