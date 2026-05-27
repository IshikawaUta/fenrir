import pytest
from fenrir import Fenrir, APIRouter, Route
from fenrir.testing import TestClient

class CustomRoute(Route):
    def __init__(self, path_pattern, handler, methods=None):
        super().__init__(path_pattern, handler, methods)
        self.custom_attribute = "custom-route-meta"


@pytest.mark.anyio
async def test_custom_route_class():
    # Test Router with custom route class
    router = APIRouter(route_class=CustomRoute)

    @router.route("/hello")
    def hello():
        return "hi"

    assert len(router.routes) == 1
    route = router.routes[0]
    assert isinstance(route, CustomRoute)
    assert route.custom_attribute == "custom-route-meta"


@pytest.mark.anyio
async def test_circular_router_inclusion():
    router_a = APIRouter()
    router_b = APIRouter()

    # Self inclusion
    with pytest.raises(RuntimeError) as exc_info:
        router_a.include_router(router_a)
    assert "Cannot include a router into itself" in str(exc_info.value)

    # Simple circular inclusion (A -> B, B -> A)
    router_a.include_router(router_b)
    with pytest.raises(RuntimeError) as exc_info:
        router_b.include_router(router_a)
    assert "Circular router inclusion detected" in str(exc_info.value)
