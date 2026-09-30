from app.execution.api_read_provider import ApiReadProvider
from app.execution.base import (
    CancelResult,
    ExecutionResult,
    PreflightResult,
    VerificationResult,
)
from app.services.action_registry import ActionEnvelope, ActionName
from app.services.api_client import ApiError
from app.services.api_endpoint_map import EndpointMap


class ApiExecutionProvider:
    def __init__(self, client, advertiser_id: int) -> None:
        self.client = client
        self.advertiser_id = advertiser_id
        self.endpoints = EndpointMap.default()
        self.read_provider = ApiReadProvider(client, advertiser_id)

    async def preflight(self, action: ActionEnvelope) -> PreflightResult:
        if action.action_name == ActionName.CREATE_PLAN:
            return PreflightResult(ok=True, before={})
        try:
            before = self.read_provider.get_plan(action.target_id).model_dump()
        except (KeyError, ValueError) as exc:
            return PreflightResult(ok=False, before={}, message=str(exc))
        return PreflightResult(ok=True, before=before)

    async def execute(self, action: ActionEnvelope) -> ExecutionResult:
        from app.execution.base import UnknownExecutionState

        request = self.endpoints.build(action, self.advertiser_id)
        try:
            before = await self.preflight(action)
            if not before.ok:
                raise ValueError(before.message)
            self.client.request(request.method, request.path, json=request.payload)
            after = {}
            if action.action_name != ActionName.CREATE_PLAN:
                after = self.read_provider.get_plan(action.target_id).model_dump()
        except ApiError as exc:
            raise UnknownExecutionState(str(exc)) from exc
        return ExecutionResult(
            action={
                "action_name": action.action_name.value,
                "target_id": action.target_id,
                "params": action.params,
            },
            before=before.before,
            after=after,
        )
    async def verify(
        self,
        action: ActionEnvelope,
        result: ExecutionResult,
    ) -> VerificationResult:
        if action.action_name == ActionName.CREATE_PLAN:
            return VerificationResult(
                ok=True,
                before=result.before,
                after=result.after,
                message="created",
            )
        if action.action_name == ActionName.DELETE_PLAN:
            try:
                self.read_provider.get_plan(action.target_id)
            except KeyError:
                return VerificationResult(
                    ok=True,
                    before=result.before,
                    after={"deleted": True},
                )
            return VerificationResult(
                ok=False,
                before=result.before,
                after=result.after,
                message="plan still exists",
            )

        current = self.read_provider.get_plan(action.target_id).model_dump()
        expected = dict(result.before)
        if action.action_name == ActionName.PAUSE_PLAN:
            expected["status"] = "paused"
        elif action.action_name == ActionName.ENABLE_PLAN:
            expected["status"] = "active"
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            expected["budget"] = float(action.params["budget"])
        elif action.action_name == ActionName.COPY_PLAN:
            expected["name"] = action.params["name"]
        elif action.action_name == ActionName.EDIT_PLAN:
            expected.update(action.params["fields"])
        elif action.action_name == ActionName.UPDATE_PLAN_BID:
            expected["bid"] = float(action.params["bid"])
        elif action.action_name == ActionName.UPDATE_TARGETING:
            expected["targeting"] = action.params["targeting"]
        elif action.action_name == ActionName.UPDATE_SCHEDULE:
            expected["schedule"] = action.params["schedule"]
        elif action.action_name == ActionName.BIND_EXISTING_MATERIAL:
            expected["materials"] = [
                *result.before.get("materials", []),
                action.params["material_id"],
            ]
        elif action.action_name == ActionName.UNBIND_EXISTING_MATERIAL:
            expected["materials"] = [
                item
                for item in result.before.get("materials", [])
                if item != action.params["material_id"]
            ]
        ok = current == expected
        return VerificationResult(
            ok=ok,
            before=result.before,
            after=current,
            message="verified" if ok else "state mismatch",
        )
    async def cancel(self, job_id: str) -> CancelResult:
        return CancelResult(cancelled=False, message=f"Job {job_id} is not cancellable")