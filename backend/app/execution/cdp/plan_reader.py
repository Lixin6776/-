import json
import re
import time
from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import parse_qs, quote, urlparse

import httpx
from websockets.sync.client import connect

from app.execution.cdp.page_probe import validate_cdp_endpoint
from app.services.action_planner import PlanSnapshot

STATUS_MAP = {
    "投放中": "active",
    "已暂停": "paused",
    "审核中": "reviewing",
    "已删除": "deleted",
    "投放结束": "ended",
}


def _optional_number_after(text: str, label: str) -> float | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != label:
            continue
        for candidate in lines[index + 1 : index + 8]:
            match = re.search(r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", candidate)
            if match is not None:
                return float(match.group(1).replace(",", ""))
    return None


def parse_plan_detail_text(text: str, plan_id: str) -> PlanSnapshot:
    if f"计划ID：{plan_id}" not in text:
        raise ValueError(f"Plan ID not found in page: {plan_id}")

    status = "unknown"
    for line in text.splitlines():
        candidate = line.strip()
        if candidate in STATUS_MAP:
            status = STATUS_MAP[candidate]
            break

    budget_match = re.search(
        r"预算\(元\)：\s*每日\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
    )
    if budget_match is None:
        if re.search(r"预算\(元\)：\s*不限", text):
            budget = 0.0
        else:
            raise ValueError("Plan budget not found in page")
    else:
        budget = float(budget_match.group(1).replace(",", ""))

    account_match = re.search(r"抖音号：\s*([^\r\n]+)", text)
    account_name = account_match.group(1).strip() if account_match is not None else None
    roi_match = re.search(r"综合营销ROI目标：\s*([0-9]+(?:\.[0-9]+)?)", text)
    roi_goal = float(roi_match.group(1)) if roi_match is not None else None

    return PlanSnapshot(
        id=plan_id,
        name=f"计划 {plan_id}",
        account_name=account_name,
        status=status,
        budget=budget,
        roi_goal=roi_goal,
        roi=_optional_number_after(text, "综合营销ROI"),
        spend=_optional_number_after(text, "综合成本(元)"),
        gmv=_optional_number_after(text, "净成交金额(元)"),
        orders=(
            int(orders)
            if (orders := _optional_number_after(text, "整体成交订单数")) is not None
            else None
        ),
    )


class CdpPlanReader:
    def __init__(self, endpoint: str, advertiser_id: int | None = None) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)
        self.advertiser_id = advertiser_id

    def read_current(self) -> PlanSnapshot:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{self.endpoint}/json/list")
            response.raise_for_status()
            targets = response.json()
        return self.read(self._find_current_plan_id(targets))

    def read(self, plan_id: str) -> PlanSnapshot:
        with httpx.Client(timeout=5) as client:
            targets_response = client.get(f"{self.endpoint}/json/list")
            targets_response.raise_for_status()
            targets = targets_response.json()
            version_response = client.get(f"{self.endpoint}/json/version")
            version_response.raise_for_status()
            version = version_response.json()

        advertiser_id = str(self.advertiser_id or self._find_advertiser_id(targets))
        detail_url = self._detail_url(advertiser_id, plan_id)
        browser_ws_url = str(version["webSocketDebuggerUrl"])

        with connect(
            browser_ws_url,
            open_timeout=5,
            close_timeout=3,
            max_size=40_000_000,
        ) as websocket:
            created = self._call(
                websocket,
                1,
                "Target.createTarget",
                {"url": detail_url, "background": True},
            )
            target_id = str(created["result"]["targetId"])
            result = None
            try:
                attached = self._call(
                    websocket,
                    2,
                    "Target.attachToTarget",
                    {"targetId": target_id, "flatten": True},
                )
                session_id = str(attached["result"]["sessionId"])
                time.sleep(2)
                result = None
                for _ in range(3):
                    try:
                        result = self._call(
                            websocket,
                            3,
                            "Runtime.evaluate",
                            {
                                "expression": self._wait_expression(plan_id),
                                "awaitPromise": True,
                                "returnByValue": True,
                            },
                            session_id=session_id,
                        )
                        break
                    except RuntimeError as exc:
                        if "Execution context was destroyed" not in str(exc):
                            raise
                        time.sleep(1)
                if result is None:
                    raise RuntimeError("Plan page context did not become ready")
            finally:
                with suppress(OSError, RuntimeError, TimeoutError):
                    self._call(
                        websocket,
                        99,
                        "Target.closeTarget",
                        {"targetId": target_id},
                    )

        if result is None:
            raise RuntimeError("Could not attach to the plan page")
        value = result.get("result", {}).get("result", {}).get("value")
        if not isinstance(value, dict) or not value.get("ok"):
            page_text = value.get("text", "") if isinstance(value, dict) else ""
            raise RuntimeError(f"Could not read plan page: {page_text[:200]}")
        return parse_plan_detail_text(str(value["text"]), plan_id)

    @staticmethod
    def _find_current_plan_id(targets: list[dict]) -> str:
        for target in targets:
            url = str(target.get("url", ""))
            if "overall-prom/detail" not in url:
                continue
            query = parse_qs(urlparse(url).query)
            plan_id = query.get("adId", [None])[0]
            if plan_id:
                return str(plan_id)
        raise RuntimeError("Current Qianchuan plan id was not found in CDP targets")

    @staticmethod
    def _find_advertiser_id(targets: list[dict]) -> str:
        for target in targets:
            url = str(target.get("url", ""))
            if "qianchuan" not in url:
                continue
            query = parse_qs(urlparse(url).query)
            advertiser_id = query.get("aavid", [None])[0]
            if advertiser_id:
                return str(advertiser_id)
        raise RuntimeError("Qianchuan advertiser id was not found in CDP targets")

    @staticmethod
    def _detail_url(advertiser_id: str, plan_id: str) -> str:
        today = datetime.now(UTC).date().isoformat()
        return (
            "https://qianchuan.jinritemai.com/overall-prom/detail"
            f"?aavid={quote(advertiser_id)}&campaignType=1&uniTab=ad"
            f"&adId={quote(plan_id)}&dateRange={today}%2C{today}#?marGoal=2"
        )

    @staticmethod
    def _wait_expression(plan_id: str) -> str:
        target = json.dumps(plan_id, ensure_ascii=False)
        return f'''(async () => {{
  const targetId = {target};
  for (let index = 0; index < 50; index += 1) {{
    const text = document.body ? document.body.innerText : "";
    if (text.includes("计划ID：" + targetId) && text.includes("综合营销ROI")) {{
      return {{ok: true, text, url: location.href}};
    }}
    await new Promise((resolve) => setTimeout(resolve, 400));
  }}
  return {{
    ok: false,
    text: document.body ? document.body.innerText : "",
    url: location.href,
  }};
}})()'''

    @staticmethod
    def _call(websocket, request_id, method, params=None, session_id=None):
        payload = {"id": request_id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        websocket.send(json.dumps(payload))
        while True:
            message = json.loads(websocket.recv(timeout=20))
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message
