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
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            predefined = model_instance.predefined_models()
            if predefined:
                logger.info("Validating Runware credentials against %s", predefined[0].model)
                model_instance.validate_credentials(
                    model=predefined[0].model, credentials=credentials
                )
            else:
                logger.info("No predefined Runware models yet; accepting credentials without a probe.")
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            logger.exception("Runware credentials validation failed")
            raise CredentialsValidateFailedError(str(ex)) from ex
