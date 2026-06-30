from unittest.mock import MagicMock, patch

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import ModelFeature, ModelPropertyKey
from dify_plugin.entities.model.llm import LLMMode

from models.llm.llm import DEFAULT_ENDPOINT, RunwareLargeLanguageModel


def _model() -> RunwareLargeLanguageModel:
    return object.__new__(RunwareLargeLanguageModel)


class TestUpdateCredentials:
    def test_fills_default_endpoint_and_mode(self):
        model = _model()
        model.get_model_schema = MagicMock(return_value=None)
        credentials = {"api_key": "sk-test"}

        model._update_credentials("some-model", credentials)

        assert credentials["endpoint_url"] == DEFAULT_ENDPOINT
        assert credentials["mode"] == LLMMode.CHAT.value

    def test_preserves_explicit_endpoint_and_mode(self):
        model = _model()
        model.get_model_schema = MagicMock(return_value=None)
        credentials = {
            "api_key": "sk-test",
            "endpoint_url": "https://custom.example.com/v1/",
            "mode": "completion",
        }

        model._update_credentials("some-model", credentials)

        assert credentials["endpoint_url"] == "https://custom.example.com/v1/"
        assert credentials["mode"] == "completion"

    def test_infers_tool_call_from_schema_features(self):
        model = _model()
        schema = MagicMock(features=[ModelFeature.TOOL_CALL, ModelFeature.VISION])
        model.get_model_schema = MagicMock(return_value=schema)
        credentials = {"api_key": "sk-test"}

        model._update_credentials("anthropic-claude-opus-4-8", credentials)

        assert credentials["function_calling_type"] == "tool_call"
        assert credentials["stream_function_calling"] == "supported"

    def test_no_tool_call_feature_leaves_credentials_untouched(self):
        model = _model()
        schema = MagicMock(features=[ModelFeature.VISION])
        model.get_model_schema = MagicMock(return_value=schema)
        credentials = {"api_key": "sk-test"}

        model._update_credentials("some-model", credentials)

        assert "function_calling_type" not in credentials

    def test_does_not_override_explicit_function_calling_type(self):
        model = _model()
        model.get_model_schema = MagicMock()
        credentials = {"api_key": "sk-test", "function_calling_type": "no_call"}

        model._update_credentials("some-model", credentials)

        model.get_model_schema.assert_not_called()
        assert credentials["function_calling_type"] == "no_call"


class TestDelegatesToBaseAfterUpdatingCredentials:
    def test_invoke(self):
        model = _model()
        model._update_credentials = MagicMock()
        with patch.object(OAICompatLargeLanguageModel, "_invoke", return_value="ok") as base:
            result = model._invoke("m", {"api_key": "x"}, [], {})

        model._update_credentials.assert_called_once_with("m", {"api_key": "x"})
        base.assert_called_once()
        assert result == "ok"

    def test_validate_credentials(self):
        model = _model()
        model._update_credentials = MagicMock()
        with patch.object(OAICompatLargeLanguageModel, "validate_credentials") as base:
            model.validate_credentials("m", {"api_key": "x"})

        model._update_credentials.assert_called_once_with("m", {"api_key": "x"})
        base.assert_called_once()

    def test_get_num_tokens(self):
        model = _model()
        model._update_credentials = MagicMock()
        with patch.object(OAICompatLargeLanguageModel, "get_num_tokens", return_value=42) as base:
            result = model.get_num_tokens("m", {"api_key": "x"}, [])

        model._update_credentials.assert_called_once_with("m", {"api_key": "x"})
        assert result == 42


class TestCustomizableModelSchema:
    def test_minimal_credentials_use_defaults(self):
        model = _model()

        schema = model.get_customizable_model_schema("custom-model", {})

        assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 8192
        assert ModelFeature.TOOL_CALL not in (schema.features or [])
        assert ModelFeature.VISION not in (schema.features or [])

    def test_tool_call_and_vision_flags_add_features(self):
        model = _model()
        credentials = {
            "context_size": "32000",
            "max_tokens_to_sample": "8000",
            "function_calling_type": "tool_call",
            "vision_support": "support",
        }

        schema = model.get_customizable_model_schema("custom-model", credentials)

        assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 32000
        assert ModelFeature.TOOL_CALL in schema.features
        assert ModelFeature.MULTI_TOOL_CALL in schema.features
        assert ModelFeature.VISION in schema.features
        max_tokens_rule = next(r for r in schema.parameter_rules if r.name == "max_tokens")
        assert max_tokens_rule.max == 8000
