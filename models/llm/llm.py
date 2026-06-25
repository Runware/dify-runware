from collections.abc import Generator
from typing import Optional, Union

from yarl import URL

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

DEFAULT_ENDPOINT = "https://api.runware.ai/v1"


class RunwareLargeLanguageModel(OAICompatLargeLanguageModel):
    """
    Runware LLM. Runware exposes an OpenAI-compatible /v1/chat/completions
    endpoint, so the OAICompat base handles the wire protocol. We only inject
    the credential keys the base requires (`endpoint_url`, `mode`) so that
    predefined models — whose credentials come from the provider-level schema —
    work without per-model configuration.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        self._update_credentials(model, credentials)
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credentials(model, credentials)
        super().validate_credentials(model, credentials)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        self._update_credentials(model, credentials)
        return super().get_num_tokens(model, credentials, prompt_messages, tools)

    def _update_credentials(self, model: str, credentials: dict) -> None:
        credentials["endpoint_url"] = str(URL(credentials.get("endpoint_url") or DEFAULT_ENDPOINT))
        credentials["mode"] = credentials.get("mode") or LLMMode.CHAT.value

        if "function_calling_type" not in credentials:
            schema = self.get_model_schema(model, credentials)
            features = (schema.features or []) if schema else []
            if {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL}.intersection(features):
                credentials["function_calling_type"] = "tool_call"
                credentials.setdefault("stream_function_calling", "supported")

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """Schema for the customizable-model fallback path."""
        features: list[ModelFeature] = []
        if credentials.get("function_calling_type") == "tool_call":
            features.extend(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
            )
        if credentials.get("vision_support") == "support":
            features.append(ModelFeature.VISION)

        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=features,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 8192)),
                ModelPropertyKey.MODE: credentials.get("mode") or LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_us="Temperature", zh_hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_k",
                    use_template="top_k",
                    label=I18nObject(en_us="Top K", zh_hans="Top K"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=1024,
                    min=1,
                    max=int(credentials.get("max_tokens_to_sample", 4096)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="frequency_penalty",
                    use_template="frequency_penalty",
                    label=I18nObject(en_us="Frequency Penalty", zh_hans="频率惩罚"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="presence_penalty",
                    use_template="presence_penalty",
                    label=I18nObject(en_us="Presence Penalty", zh_hans="存在惩罚"),
                    type=ParameterType.FLOAT,
                ),
            ],
        )
