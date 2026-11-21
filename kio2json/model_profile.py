"""Choose extraction and routing for the bundled organizer registry."""

from typing import Literal, NamedTuple

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["R", "L", "RL", "LR", "V"]
RoutingPolicy = Literal["rules", "fallback", "model"]


class Profile(NamedTuple):
    mode: Mode = "R"
    routing: RoutingPolicy = "rules"
    dual_ocr: bool = False


class ProfileSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KIO_LLM_", env_file=".env", extra="ignore", hide_input_in_errors=True)
    base_url: str = ""
    model: str = ""
    api_key: SecretStr = SecretStr("")
    mode: Mode = "LR"
    routing: RoutingPolicy = "fallback"
    dual_ocr: bool = True

    def profile(self) -> Profile:
        if self.base_url.strip() and self.model.strip() and self.api_key.get_secret_value().strip():
            return Profile(self.mode, self.routing, self.dual_ocr and (self.mode != "R" or self.routing != "rules"))
        return Profile()
