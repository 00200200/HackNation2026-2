"""Choose extraction and routing for the bundled organizer registry."""

from typing import Literal, NamedTuple

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["R", "L", "RL", "LR", "V"]
RoutingPolicy = Literal["rules", "fallback", "model", "supported"]


GapScope = Literal["all", "incomplete"]


class Profile(NamedTuple):
    mode: Mode = "R"
    routing: RoutingPolicy = "rules"
    dual_ocr: bool = False
    keyed: bool = False
    gap_scope: GapScope = "all"

    jury: bool = False

    @property
    def rules_first(self) -> bool:
        return not self.keyed or self.mode == "RL"


class ProfileSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KIO_LLM_", env_file=".env", extra="ignore", hide_input_in_errors=True)
    base_url: str = ""
    model: str = ""
    api_key: SecretStr = SecretStr("")
    mode: Mode = "LR"
    routing: RoutingPolicy = "fallback"
    dual_ocr: bool = True
    gap_scope: GapScope = "all"

    def profile(self) -> Profile:
        if self.base_url.strip() and self.model.strip() and self.api_key.get_secret_value().strip():
            if (
                self.base_url.rstrip("/") == "https://api.eu.mistral.ai/v1"
                and self.model == "ministral-3b-2512"
                and not self.model_fields_set.intersection({"mode", "routing", "dual_ocr", "gap_scope"})
            ):
                return Profile(mode="RL", routing="rules", keyed=True, jury=True)
            return Profile(
                self.mode,
                self.routing,
                self.dual_ocr and (self.mode != "R" or self.routing != "rules"),
                True,
                self.gap_scope,
            )
        return Profile()
