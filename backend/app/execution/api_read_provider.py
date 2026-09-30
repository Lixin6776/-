from app.execution.cdp.page_adapter import PlanPageSnapshot
from app.services.api_endpoint_map import EndpointMap


class ApiReadProvider:
    def __init__(self, client, advertiser_id: int) -> None:
        self.client = client
        self.advertiser_id = advertiser_id
        self.endpoints = EndpointMap.read_endpoints()

    def get_plan(self, plan_id: str) -> PlanPageSnapshot:
        method, path = self.endpoints["plan_list"]
        response = self.client.request(
            method,
            path,
            params={"advertiser_id": self.advertiser_id},
        )
        plans = response.json()["data"]["list"]
        for item in plans:
            if str(item["ad_id"]) == str(plan_id):
                return PlanPageSnapshot(
                    id=str(item["ad_id"]),
                    name=str(item["ad_name"]),
                    status=str(item["status"]),
                    budget=float(item["budget"]),
                    bid=float(item["bid"]) if item.get("bid") is not None else None,
                    targeting=dict(item.get("targeting", {})),
                    schedule=dict(item.get("schedule", {})),
                    materials=list(item.get("materials", [])),
                    available_materials=list(item.get("available_materials", [])),
                )
        raise KeyError(f"Plan not found in API response: {plan_id}")

    def get_account(self) -> dict:
        method, path = self.endpoints["account_info"]
        return self.client.request(
            method,
            path,
            params={"advertiser_id": self.advertiser_id},
        ).json()["data"]

    def get_reports(self, report_type: str = "plan_report") -> dict:
        method, path = self.endpoints[report_type]
        return self.client.request(
            method,
            path,
            params={"advertiser_id": self.advertiser_id},
        ).json()["data"]