"""LLM 抽象层 —— 本地模型和云端模型一视同仁。

思念不绑定任何一家模型。能跑 Ollama 就本地跑（隐私最好），
想用云端就走 OpenAI 兼容协议（DeepSeek / 通义 / Kimi 都兼容）。

httpx 是可选依赖：pip install sinian[llm]
不用 LLM 功能（纯统计侧写）时不需要装它。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """大模型提供者基类。"""

    @abstractmethod
    def chat(self, system: str, messages: list[dict]) -> str:
        """system = 人格组装的提示词；messages = 对话历史。"""
        raise NotImplementedError

    @staticmethod
    def _httpx():
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError(
                "调 LLM 需要 httpx：pip install httpx（或 pip install sinian[llm]）"
            ) from e
        return httpx


class OllamaProvider(LLMProvider):
    """本地 Ollama。数据不出机，纪念之物就该放在自己手里。"""

    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://127.0.0.1:11434",
                 timeout: float = 120.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, messages: list[dict]) -> str:
        httpx = self._httpx()
        resp = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": system}, *messages],
                "stream": False,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容协议 —— 一套代码吃遍云端。"""

    def __init__(self, api_key: str, model: str,
                 base_url: str = "https://api.openai.com/v1", timeout: float = 120.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, messages: list[dict]) -> str:
        httpx = self._httpx()
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": system}, *messages],
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
