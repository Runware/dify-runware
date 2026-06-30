from unittest.mock import MagicMock

import pytest
from dify_plugin.errors.model import CredentialsValidateFailedError

from provider.runware import RunwareProvider


def _provider() -> RunwareProvider:
    return object.__new__(RunwareProvider)


class TestIsModelUnavailable:
    @pytest.mark.parametrize(
        "message",
        [
            "model not_found: anthropic-claude-fable-5",
            "404 model not available",
            "the requested model is unavailable",
        ],
    )
    def test_treats_404_style_messages_as_unavailable(self, message):
        assert RunwareProvider._is_model_unavailable(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "401 Unauthorized",
            "invalid api key provided",
            "403 forbidden",
        ],
    )
    def test_treats_auth_errors_as_not_unavailable(self, message):
        assert RunwareProvider._is_model_unavailable(message) is False

    def test_auth_signal_wins_over_unavailable_keyword(self):
        assert RunwareProvider._is_model_unavailable("401 unauthorized: model not_found") is False


class TestValidateProviderCredentials:
    def test_accepts_when_no_predefined_models_yet(self):
        provider = _provider()
        model_instance = MagicMock()
        model_instance.predefined_models.return_value = []
        provider.get_model_instance = MagicMock(return_value=model_instance)

        provider.validate_provider_credentials({"api_key": "sk-test"})

        model_instance.validate_credentials.assert_not_called()

    def test_validates_against_first_predefined_model(self):
        provider = _provider()
        predefined = MagicMock(model="anthropic-claude-opus-4-8")
        model_instance = MagicMock()
        model_instance.predefined_models.return_value = [predefined]
        provider.get_model_instance = MagicMock(return_value=model_instance)
        credentials = {"api_key": "sk-test"}

        provider.validate_provider_credentials(credentials)

        model_instance.validate_credentials.assert_called_once_with(
            model="anthropic-claude-opus-4-8", credentials=credentials
        )

    def test_accepts_when_probe_model_unavailable_but_key_valid(self):
        provider = _provider()
        predefined = MagicMock(model="anthropic-claude-fable-5")
        model_instance = MagicMock()
        model_instance.predefined_models.return_value = [predefined]
        model_instance.validate_credentials.side_effect = CredentialsValidateFailedError("404 not_found")
        provider.get_model_instance = MagicMock(return_value=model_instance)

        provider.validate_provider_credentials({"api_key": "sk-test"})  # must not raise

    def test_raises_on_real_auth_failure(self):
        provider = _provider()
        predefined = MagicMock(model="anthropic-claude-opus-4-8")
        model_instance = MagicMock()
        model_instance.predefined_models.return_value = [predefined]
        model_instance.validate_credentials.side_effect = CredentialsValidateFailedError("401 unauthorized")
        provider.get_model_instance = MagicMock(return_value=model_instance)

        with pytest.raises(CredentialsValidateFailedError):
            provider.validate_provider_credentials({"api_key": "sk-test"})

    def test_wraps_unexpected_setup_error(self):
        provider = _provider()
        provider.get_model_instance = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(CredentialsValidateFailedError):
            provider.validate_provider_credentials({"api_key": "sk-test"})
