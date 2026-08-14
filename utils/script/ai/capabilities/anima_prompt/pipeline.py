from __future__ import annotations

from dataclasses import dataclass
import re

from utils.script.ai.kernel import AiProvider, OpenAiCompatClient
from utils.script.image.anima.prompt_doc import PromptDoc

from .prompts import build_messages


PromptViolation = tuple[str, str]


_REFUSAL_PATTERNS = (
    re.compile(r"\bi\s+(?:can not|cannot|can't)\b"),
    re.compile(r"\bi\s+(?:am|was)\s+sorry\b"),
    re.compile(r"\bas\s+an\s+ai\b"),
    re.compile(r"\b(?:service\s+secrets|environment\s+variables|private\s+deployment\s+metadata)\b"),
    re.compile(r"\b(?:cannot|can't|unable to)\s+(?:provide|return|share|disclose|reveal)\b"),
)


def reject_unusable_response(content: object) -> str:
    """只拦「根本不是 prompt」的响应，返回可继续加工的原文。

    必须与「格式违规」分开：拒答/散文会被 PromptDoc 当成合法 body token 解析，
    这是 LLM 道德拒答整段变成 prompt 的根因，只能在解析前拦。
    而下划线 / 未转义括号 / artist 缺 @ 是**可恢复**的，规范化管道本就为此存在；
    把它们一并拒掉等于因为模型写了 long_hair 就丢弃一次完全可用的回答。
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI returned an empty prompt")

    response_text = content.strip()
    searchable_text = " ".join(response_text.lower().split())
    if any(pattern.search(searchable_text) for pattern in _REFUSAL_PATTERNS):
        raise ValueError("AI response did not contain a usable ANIMA prompt")
    # 系统提示词要求单行 prompt；代码块 / 换行是散文与解释的最廉价信号。
    if "```" in response_text or "\n" in response_text or "\r" in response_text:
        raise ValueError("AI response did not contain a usable ANIMA prompt")
    return response_text


@dataclass(frozen=True, slots=True)
class AnimaPromptResult:
    """`text` 是规范化后的成品；`raw_text` 与 `violations` 一起用于告知用户模型没守规矩。

    刻意不为 text/raw_text 再挂别名属性：一个字段多个名字，调用方迟早各用各的。
    """

    text: str
    raw_text: str
    violations: list[PromptViolation]


class AnimaPromptPipeline:
    def __init__(
        self,
        provider: AiProvider,
        *,
        proxies: object = None,
        client: object | None = None,
        timeout: float = 90.0,
    ):
        if provider is None:
            raise ValueError("AnimaPromptPipeline requires an AI provider")
        self.provider = provider
        self.proxies = proxies
        self.client = (
            client
            if client is not None
            else OpenAiCompatClient(provider, proxies=proxies, timeout=timeout)
        )

    def run(
        self,
        *,
        tag_context: str,
        nl_instruction: str,
        preset: str,
        known: dict[str, str] | None = None,
    ) -> AnimaPromptResult:
        if not self.provider.is_configured():
            raise ValueError("AI provider is not configured")
        messages = build_messages(
            tag_context=tag_context,
            nl_instruction=nl_instruction,
            preset=preset,
        )
        content = self.client.chat_content(messages)
        response_text = reject_unusable_response(content)
        normalized_text = PromptDoc.from_text(response_text, known=known).to_text()
        if not normalized_text:
            raise ValueError("AI response did not contain a usable ANIMA prompt")
        # 用 normalize=False 再解析一次，拿到模型「没守规矩」的清单交给高亮器。
        # 之前这里写死 [] —— 字段永远为空，等于接口对调用方撒谎。
        raw_document = PromptDoc.from_text(response_text, known=known, normalize=False)
        return AnimaPromptResult(
            text=normalized_text,
            raw_text=response_text,
            violations=list(raw_document.violations()),
        )
