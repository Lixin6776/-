import json

import httpx
import pytest

from app.config import Settings
from app.execution.api_provider import ApiExecutionProvider
from app.services.action_registry import ActionEnvelope, ActionName
from app.services.api_client import OceanEngineApiClient
from app.services.provider_router import ProviderRouter


class ApiState:
    def __init__(self):
        self.status = "active"


def test_api_migration_acceptance_uses_mock_transport():
    state = ApiState()

    def handler(request: httpx.Request) -> httpx.Response:
        if "status/update" in request.url.path:
            state.status = "paused"
            return httpx.Response(200, json={"code": 0, "data": {}})
        if "ad/get" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "list": [
                            {
                                "ad_id": "plan-1",
                                "ad_name": "计划 A",
                                "status": state.status,
                                "budget": 1000,
                            }
                        ]
                    },
                },
            )
        return httpx.Response(404, json={"code": 404})

    config = Settings(
        api_app_id="123",
        api_app_secret="secret",
        api_access_token="token-1",
        api_token_expires_at=10_000,
    )
    client = OceanEngineApiClient(
        config=config,
        transport=httpx.MockTransport(handler),
        now=lambda: 1,
    )
    provider = ApiExecutionProvider(client, advertiser_id=123)
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    result = provider_adapter_execute(provider, action)
    assert provider_adapter_verify(provider, action, result).ok is True


def provider_adapter_execute(provider, action):
    import asyncio

    return asyncio.run(provider.execute(action))


def provider_adapter_verify(provider, action, result):
    import asyncio

    return asyncio.run(provider.verify(action, result))


def test_mutation_started_disables_cdp_fallback():
    router = ProviderRouter(
        api_provider=object(),
        cdp_provider=object(),
        api_configured=True,
        api_actions={ActionName.PAUSE_PLAN},
    )
    assert router.can_fallback(mutation_started=False) is True
    assert router.can_fallback(mutation_started=True) is False

@pytest.mark.asyncio
async def test_api_mutation_failure_is_unknown_not_retried():
    from app.execution.api_provider import ApiExecutionProvider
    from app.execution.base import UnknownExecutionState
    from app.services.action_registry import ActionEnvelope, ActionName
    from app.services.api_client import ApiAuthenticationError

    class FailingClient:
        def request(self, method, path, params=None, json=None):
            raise ApiAuthenticationError("refresh failed")

    provider = ApiExecutionProvider(FailingClient(), advertiser_id=123)
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    with pytest.raises(UnknownExecutionState):
        await provider.execute(action)


def test_api_parity_acceptance_round_trip():
    plans = {}
    next_plan_number = 2

    def snapshot(plan_id):
        plan = plans[plan_id]
        return {
            "ad_id": plan_id,
            "ad_name": plan["name"],
            "status": plan["status"],
            "budget": plan["budget"],
            "bid": plan.get("bid"),
            "targeting": plan.get("targeting", {}),
            "schedule": plan.get("schedule", {}),
            "materials": list(plan.get("materials", [])),
            "available_materials": list(plan.get("available_materials", [])),
        }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal next_plan_number
        payload = json.loads(request.content) if request.content else {}
        path = request.url.path

        if path.endswith("/ad/get/"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"list": [snapshot(plan_id) for plan_id in plans]}},
            )
        if path.endswith("/ad/create/"):
            plan_id = f"plan-{next_plan_number}"
            next_plan_number += 1
            plans[plan_id] = {
                "name": payload["name"],
                "status": "active",
                "budget": float(payload["budget"]),
                "bid": None,
                "targeting": {},
                "schedule": {},
                "materials": [],
                "available_materials": ["material-1"],
            }
            return httpx.Response(200, json={"code": 0, "data": {"ad_id": plan_id}})
        if path.endswith("/ad/copy/"):
            plan_id = f"plan-{next_plan_number}"
            next_plan_number += 1
            copied = dict(plans[payload["source_ad_id"]])
            copied["name"] = payload["name"]
            plans[plan_id] = copied
            return httpx.Response(200, json={"code": 0, "data": {"ad_id": plan_id}})
        if path.endswith("/ad/delete/"):
            del plans[payload["ad_id"]]
            return httpx.Response(200, json={"code": 0, "data": {}})
        if path.endswith("/status/update/"):
            status = "paused" if payload["opt_status"] == "disable" else "active"
            for plan_id in payload["ad_ids"]:
                plans[plan_id]["status"] = status
            return httpx.Response(200, json={"code": 0, "data": {}})
        if path.endswith("/ad/update/budget/"):
            plans[payload["ad_id"]]["budget"] = float(payload["budget"])
            return httpx.Response(200, json={"code": 0, "data": {}})
        if path.endswith("/ad/update/bid/"):
            plans[payload["ad_id"]]["bid"] = float(payload["bid"])
            return httpx.Response(200, json={"code": 0, "data": {}})
        if path.endswith("/ad/update/"):
            plan = plans[payload["ad_id"]]
            if "fields" in payload:
                plan.update(payload["fields"])
            elif "targeting" in payload:
                plan["targeting"] = payload["targeting"]
            elif "schedule" in payload:
                plan["schedule"] = payload["schedule"]
            return httpx.Response(200, json={"code": 0, "data": {}})
        if path.endswith("/ad/material/bind/"):
            plan = plans[payload["ad_id"]]
            plan.setdefault("materials", []).append(payload["material_id"])
            return httpx.Response(200, json={"code": 0, "data": {}})
        if path.endswith("/ad/material/unbind/"):
            plan = plans[payload["ad_id"]]
            plan["materials"] = [
                item for item in plan.get("materials", []) if item != payload["material_id"]
            ]
            return httpx.Response(200, json={"code": 0, "data": {}})
        return httpx.Response(404, json={"code": 404})

    config = Settings(
        api_app_id="123",
        api_app_secret="secret",
        api_access_token="token-1",
        api_token_expires_at=10_000,
    )
    client = OceanEngineApiClient(
        config=config,
        transport=httpx.MockTransport(handler),
        now=lambda: 1,
    )
    provider = ApiExecutionProvider(client, advertiser_id=123)

    create = ActionEnvelope(
        action_name=ActionName.CREATE_PLAN,
        target_id="source-product-1",
        params={
            "source_product_id": "source-product-1",
            "name": "新计划",
            "budget": 500,
            "roi_goal": 2.5,
        },
    )
    create_result = provider_adapter_execute(provider, create)
    assert create_result.after["id"] == "plan-2"
    assert provider_adapter_verify(provider, create, create_result).ok is True

    copy = ActionEnvelope(
        action_name=ActionName.COPY_PLAN,
        target_id="plan-2",
        params={"name": "复制计划"},
    )
    copy_result = provider_adapter_execute(provider, copy)
    assert copy_result.after["id"] == "plan-3"
    assert provider_adapter_verify(provider, copy, copy_result).ok is True

    for action in [
        ActionEnvelope(
            action_name=ActionName.EDIT_PLAN,
            target_id="plan-3",
            params={"fields": {"name": "复制计划-编辑"}},
        ),
        ActionEnvelope(
            action_name=ActionName.UPDATE_PLAN_BID,
            target_id="plan-3",
            params={"bid": 3.2},
        ),
        ActionEnvelope(
            action_name=ActionName.UPDATE_TARGETING,
            target_id="plan-3",
            params={"targeting": {"gender": "female"}},
        ),
        ActionEnvelope(
            action_name=ActionName.UPDATE_SCHEDULE,
            target_id="plan-3",
            params={"schedule": {"days": ["mon"]}},
        ),
        ActionEnvelope(
            action_name=ActionName.BIND_EXISTING_MATERIAL,
            target_id="plan-3",
            params={"material_id": "material-1"},
        ),
        ActionEnvelope(
            action_name=ActionName.UNBIND_EXISTING_MATERIAL,
            target_id="plan-3",
            params={"material_id": "material-1"},
        ),
    ]:
        result = provider_adapter_execute(provider, action)
        verification = provider_adapter_verify(provider, action, result)
        assert verification.ok is True, (action.action_name, verification.message)

    delete = ActionEnvelope(
        action_name=ActionName.DELETE_PLAN,
        target_id="plan-3",
        params={"reason": "acceptance"},
    )
    delete_result = provider_adapter_execute(provider, delete)
    assert delete_result.after == {"id": "plan-3", "deleted": True}
    assert provider_adapter_verify(provider, delete, delete_result).ok is True
