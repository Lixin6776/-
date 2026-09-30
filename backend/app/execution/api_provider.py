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
        except (KeyError, ValueError, TypeError) as exc:
            return PreflightResult(ok=False, before={}, message=str(exc))
        return PreflightResult(ok=True, before=before)

    async def execute(self, action: ActionEnvelope) -> ExecutionResult:
        from app.execution.base import UnknownExecutionState

        try:
            before = await self.preflight(action)
            if not before.ok:
                raise ValueError(before.message)
            request = self.endpoints.build(action, self.advertiser_id)
            response = self.client.request(
                request.method,
                request.path,
                json=request.payload,
            )
        except ApiError as exc:
            raise UnknownExecutionState(str(exc)) from exc

        if action.action_name in {ActionName.CREATE_PLAN, ActionName.COPY_PLAN}:
            try:
                created_id = self._extract_created_plan_id(response)
            except (KeyError, TypeError, ValueError) as exc:
                raise UnknownExecutionState(
                    "API mutation succeeded but the created plan ID was not returned"
                ) from exc
            after = {"id": created_id, "name": action.params["name"]}
        elif action.action_name == ActionName.DELETE_PLAN:
            after = {"id": action.target_id, "deleted": True}
        else:
            try:
                after = self.read_provider.get_plan(action.target_id).model_dump()
            except (KeyError, TypeError, ValueError) as exc:
                raise UnknownExecutionState(
                    f"API mutation succeeded but read-back failed: {exc}"
                ) from exc

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
        if action.action_name in {ActionName.CREATE_PLAN, ActionName.COPY_PLAN}:
            created_id = result.after.get("id")
            if created_id in (None, ""):
                return VerificationResult(
                    ok=False,
                    before=result.before,
                    after={},
                    message="created plan ID is missing from the execution result",
                )
            try:
                current = self.read_provider.get_plan(str(created_id)).model_dump()
            except (KeyError, TypeError, ValueError) as exc:
                return VerificationResult(
                    ok=False,
                    before=result.before,
                    after={},
                    message=str(exc),
                )
            ok = current.get("name") == action.params["name"]
            return VerificationResult(
                ok=ok,
                before=result.before,
                after=current,
                message="verified" if ok else "created plan name mismatch",
            )

        if action.action_name == ActionName.DELETE_PLAN:
            try:
                self.read_provider.get_plan(action.target_id)
            except KeyError:
                return VerificationResult(
                    ok=True,
                    before=result.before,
                    after={"id": action.target_id, "deleted": True},
                    message="deleted",
                )
            except (TypeError, ValueError) as exc:
                return VerificationResult(
                    ok=False,
                    before=result.before,
                    after={},
                    message=f"could not verify deletion: {exc}",
                )
            return VerificationResult(
                ok=False,
                before=result.before,
                after=result.after,
                message="plan still exists",
            )

        try:
            current = self.read_provider.get_plan(action.target_id).model_dump()
        except (KeyError, TypeError, ValueError) as exc:
            return VerificationResult(
                ok=False,
                before=result.before,
                after={},
                message=str(exc),
            )

        expected = dict(result.before)
        if action.action_name == ActionName.PAUSE_PLAN:
            expected["status"] = "paused"
        elif action.action_name == ActionName.ENABLE_PLAN:
            expected["status"] = "active"
        elif action.action_name == ActionName.UPDATE_PLAN_BUDGET:
            expected["budget"] = float(action.params["budget"])
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

    @staticmethod
    def _extract_created_plan_id(response) -> str:
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("API response body is not an object")
        return ApiExecutionProvider._first_plan_id(body.get("data", body))

    @staticmethod
    def _first_plan_id(value) -> str:
        if isinstance(value, dict):
            for key in ("ad_id", "adId", "id"):
                if key in value:
                    return ApiExecutionProvider._normalize_plan_id(value[key])
            for key in ("ad", "plan", "result", "ad_ids", "ids", "list", "items", "data"):
                if key in value:
                    try:
                        return ApiExecutionProvider._first_plan_id(value[key])
                    except ValueError:
                        pass
        elif isinstance(value, (list, tuple)):
            for item in value:
                try:
                    return ApiExecutionProvider._first_plan_id(item)
                except ValueError:
                    pass
        else:
            return ApiExecutionProvider._normalize_plan_id(value)
        raise ValueError("API response did not contain a plan ID")

    @staticmethod
    def _normalize_plan_id(value) -> str:
        if isinstance(value, (list, tuple)):
            if not value:
                raise ValueError("API response contained an empty plan ID list")
            return ApiExecutionProvider._normalize_plan_id(value[0])
        if isinstance(value, dict):
            return ApiExecutionProvider._first_plan_id(value)
        if value is None or str(value) == "":
            raise ValueError("API response contained an empty plan ID")
        return str(value)

    async def cancel(self, job_id: str) -> CancelResult:
        return CancelResult(cancelled=False, message=f"Job {job_id} is not cancellable")
