from dataclasses import dataclass

from app.services.action_registry import ActionEnvelope, ActionName


@dataclass(frozen=True)
class ApiActionRequest:
    method: str
    path: str
    payload: dict


class EndpointMap:
    def __init__(self, write_paths: dict[ActionName, tuple[str, str]]) -> None:
        self.write_paths = write_paths

    @classmethod
    def default(cls) -> "EndpointMap":
        return cls(
            {
                ActionName.PAUSE_PLAN: ("POST", "/open_api/v1.0/qianchuan/ad/status/update/"),
                ActionName.ENABLE_PLAN: ("POST", "/open_api/v1.0/qianchuan/ad/status/update/"),
                ActionName.UPDATE_PLAN_BUDGET: (
                    "POST",
                    "/open_api/v1.0/qianchuan/ad/update/budget/",
                ),
                ActionName.CREATE_PLAN: ("POST", "/open_api/v1.0/qianchuan/ad/create/"),
                ActionName.COPY_PLAN: ("POST", "/open_api/v1.0/qianchuan/ad/copy/"),
                ActionName.DELETE_PLAN: ("POST", "/open_api/v1.0/qianchuan/ad/delete/"),
                ActionName.EDIT_PLAN: ("POST", "/open_api/v1.0/qianchuan/ad/update/"),
                ActionName.UPDATE_PLAN_BID: ("POST", "/open_api/v1.0/qianchuan/ad/update/bid/"),
                ActionName.UPDATE_TARGETING: ("POST", "/open_api/v1.0/qianchuan/ad/update/"),
                ActionName.UPDATE_SCHEDULE: ("POST", "/open_api/v1.0/qianchuan/ad/update/"),
                ActionName.BIND_EXISTING_MATERIAL: (
                    "POST",
                    "/open_api/v1.0/qianchuan/ad/material/bind/",
                ),
                ActionName.UNBIND_EXISTING_MATERIAL: (
                    "POST",
                    "/open_api/v1.0/qianchuan/ad/material/unbind/",
                ),
            }
        )

    def build(self, action: ActionEnvelope, advertiser_id: int) -> ApiActionRequest:
        method, path = self.write_paths[action.action_name]
        payload = {"advertiser_id": advertiser_id, **action.params}
        if action.action_name in {ActionName.PAUSE_PLAN, ActionName.ENABLE_PLAN}:
            payload.update(
                {
                    "ad_ids": [action.target_id],
                    "opt_status": "disable" if action.action_name == ActionName.PAUSE_PLAN else "enable",
                }
            )
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            payload.update({"ad_id": action.target_id, "budget": action.params["budget"]})
        elif action.action_name in {ActionName.DELETE_PLAN, ActionName.EDIT_PLAN}:
            payload["ad_id"] = action.target_id
        elif action.action_name == ActionName.COPY_PLAN:
            payload.update({"source_ad_id": action.target_id, "name": action.params["name"]})
        return ApiActionRequest(method=method, path=path, payload=payload)

    @staticmethod
    def read_endpoints() -> dict[str, tuple[str, str]]:
        return {
            "account_info": ("GET", "/open_api/v1.0/qianchuan/advertiser/info/"),
            "plan_list": ("GET", "/open_api/v1.0/qianchuan/ad/get/"),
            "plan_report": ("GET", "/open_api/v1.0/qianchuan/report/ad/get/"),
            "live_room_report": ("GET", "/open_api/v1.0/qianchuan/report/live/get/"),
        }