from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TravelMind API"
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./travelmind.db"

    # mock: 不调用高德，返回演示数据；cache: 先读进程内缓存，未命中再调高德；
    # live: 每次调用高德，不读缓存。
    amap_mode: Literal["mock", "cache", "live"] = "mock"

    # 高德地图 Web 服务 API Key（REST 接口，不是 JS API 的 key）。
    # 未配置时，任何依赖它的能力都必须显式跳过或报错，
    # 而不是回退到一个看似合理的猜测值。
    amap_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
