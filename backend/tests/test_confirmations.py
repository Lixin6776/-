from app.services.confirmations import ConfirmationService


def test_confirmation_invalid_after_profile_version_change(profile):
    confirmation_service = ConfirmationService()
    confirmation = confirmation_service.create(
        recommendation_id="rec-1",
        action={"action_name": "update_plan_budget", "target_id": "plan-1", "budget": 800},
        profile=profile,
    )
    assert confirmation_service.validate(confirmation.id, profile.version, confirmation.preview_hash)
    assert not confirmation_service.validate(
        confirmation.id,
        profile.version + 1,
        confirmation.preview_hash,
    )


def test_confirmation_api_rejects_stale_profile_version(client, profile):
    payload = {
        "recommendation_id": "rec-1",
        "action": {"action_name": "update_plan_budget", "target_id": "plan-1", "budget": 800},
        "profile_version": profile.version,
    }
    created = client.post("/api/recommendations/confirmations", json=payload)
    assert created.status_code == 201
    assert created.json()["status"] == "pending"

    payload["profile_version"] = profile.version + 1
    stale = client.post("/api/recommendations/confirmations", json=payload)
    assert stale.status_code == 409