import logging

from dify_plugin import ModelProvider
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class RunwareProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials. Raises CredentialsValidateFailedError on failure.

        When predefined models exist, validate against the first one (a real
        round-trip through the OpenAI-compatible endpoint). When the predefined
        catalog is still empty, accept the credentials WITHOUT a network probe:
        a blocking/slow call here can stall the debug channel and surface as a
        500 in the UI. The key is verified for real on first model invocation.

        If the probe model is unavailable upstream (e.g. an export-restricted
        model returning 404 / not_found), the API key has still authenticated
        successfully, so the credentials are accepted: a single unavailable
        model must not block configuring the whole provider.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            predefined = model_instance.predefined_models()
        except Exception as ex:
            logger.exception("Runware provider setup failed during credential validation")
            raise CredentialsValidateFailedError(str(ex)) from ex

        if not predefined:
            logger.info("No predefined Runware models yet; accepting credentials without a probe.")
            return

        probe_model = predefined[0].model
        try:
            logger.info("Validating Runware credentials against %s", probe_model)
            model_instance.validate_credentials(model=probe_model, credentials=credentials)
        except CredentialsValidateFailedError as ex:
            if self._is_model_unavailable(str(ex)):
                logger.info(
                    "Probe model %s is unavailable upstream; the API key authenticated, "
                    "accepting provider credentials.", probe_model
                )
                return
            raise
        except Exception as ex:
            if self._is_model_unavailable(str(ex)):
                logger.info(
                    "Probe model %s is unavailable upstream; the API key authenticated, "
                    "accepting provider credentials.", probe_model
                )
                return
            logger.exception("Runware credentials validation failed")
            raise CredentialsValidateFailedError(str(ex)) from ex

    @staticmethod
    def _is_model_unavailable(message: str) -> bool:
        """
        True if a probe error indicates the *model* is unavailable (so the key
        authenticated) rather than an authentication failure. Auth signals win:
        if the message looks like 401/403, treat it as a real credential failure.
        """
        msg = message.lower()
        if any(
            token in msg
            for token in ("401", "403", "unauthorized", "forbidden", "invalid api key", "authentication")
        ):
            return False
        return any(
            token in msg
            for token in ("not_found", "not found", "not available", "unavailable", "404")
        )
