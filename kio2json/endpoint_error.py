"""Public diagnostics for failures in the model provider and its SDK."""


class EndpointError(RuntimeError):
    def __init__(self, error: Exception):
        # Provider messages can contain the response body, authorization headers or URL credentials.
        failure = type(error).__name__
        self.status: int | None = None
        # Some Pydantic AI errors leave the HTTP status on the underlying SDK exception.
        for source in (error, error.__cause__):
            status = getattr(source, "status_code", None)
            if status is None:
                status = getattr(getattr(source, "response", None), "status_code", None)
            if isinstance(status, int) and 100 <= status <= 599:
                self.status = int(status)
                failure += f", HTTP {self.status}"
                break
        super().__init__(failure)
