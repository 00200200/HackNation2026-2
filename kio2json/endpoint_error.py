"""Public diagnostics for failures in the model provider and its SDK."""


class EndpointError(RuntimeError):
    def __init__(self, error: Exception):
        # Provider messages can contain the response body, authorization headers or URL credentials.
        failure = type(error).__name__
        # Some Pydantic AI errors leave the HTTP status on the underlying SDK exception.
        for source in (error, error.__cause__):
            status = getattr(source, "status_code", None)
            if status is None:
                status = getattr(getattr(source, "response", None), "status_code", None)
            if isinstance(status, int) and 100 <= status <= 599:
                failure += f", HTTP {int(status)}"
                break
        super().__init__(failure)
