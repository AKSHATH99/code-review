class LLMError(Exception):
    pass


class LLMConfigurationError(LLMError):
    pass


class LLMConnectionError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass
