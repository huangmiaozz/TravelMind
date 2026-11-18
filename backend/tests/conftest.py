"""全局测试隔离：默认禁用真实高德调用。

需要路线/天气的测试应显式覆盖 ``get_planning_provider``；其余测试一律拿到
``None``，避免因为本地 .env 配了 Key 而在单元测试里访问外网。
"""

import pytest

from app.main import app
from app.services.planning_services import get_planning_provider


@pytest.fixture(autouse=True)
def disable_real_amap() -> None:
    app.dependency_overrides[get_planning_provider] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_planning_provider, None)
