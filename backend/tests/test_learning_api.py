from app.models import StrategySuggestion


def test_learning_suggestion_api_returns_proposed_only(client, profile, db_session):
    db_session.add(
        StrategySuggestion(
            id="s1",
            strategy_profile_version=profile.version,
            suggestion_type="threshold_adjustment",
            proposed_change={"roi_floor_delta": 0.1},
            evidence={"sample_size": 24},
            confidence="high",
            status="proposed",
        )
    )
    db_session.commit()
    response = client.get("/api/learning/suggestions")
    assert response.status_code == 200
    assert all(item["status"] == "proposed" for item in response.json())


def test_rejecting_suggestion_remembers_reason(client, profile, db_session):
    suggestion = StrategySuggestion(
        id="s2",
        strategy_profile_version=profile.version,
        suggestion_type="threshold_adjustment",
        proposed_change={"roi_floor_delta": 0.1},
        evidence={"sample_size": 24},
        confidence="high",
        status="proposed",
    )
    db_session.add(suggestion)
    db_session.commit()
    response = client.post("/api/learning/suggestions/s2/reject", json={"reason": "样本不足"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["evidence"]["rejection_reason"] == "样本不足"

def test_chat_can_include_learning_context(client, profile, db_session):
    from app.api.chat import get_llm_provider
    from app.main import app
    from app.services.llm.base import LLMMessage, LLMResponse

    captured: list[LLMMessage] = []

    class CapturingProvider:
        async def complete(self, messages, tools):
            captured.extend(messages)
            return LLMResponse(content='{"kind":"analysis","message":"已结合学习记录。"}')

    app.dependency_overrides[get_llm_provider] = lambda: CapturingProvider()
    response = client.post(
        "/api/chat",
        json={"message": "为什么需要学习记录", "include_learning_context": True},
    )
    assert response.status_code == 200
    assert any("learning_context" in message.content for message in captured)

def test_accept_suggestion_creates_inactive_draft_with_adjustment(client, profile, db_session):
    from app.models import StrategyProfile

    suggestion = StrategySuggestion(
        id="s3",
        strategy_profile_version=profile.version,
        suggestion_type="threshold_adjustment",
        proposed_change={"roi_floor_delta": 0.1},
        evidence={"sample_size": 24},
        confidence="high",
        status="proposed",
    )
    db_session.add(suggestion)
    db_session.commit()
    response = client.post("/api/learning/suggestions/s3/accept")
    assert response.status_code == 200
    draft = db_session.query(StrategyProfile).filter_by(version=profile.version + 1).one()
    assert draft.active is False
    assert draft.hard_constraints["learning_adjustments"] == {"roi_floor_delta": 0.1}
