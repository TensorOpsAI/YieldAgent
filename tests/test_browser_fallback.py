from yieldagent.integrations.browser_fallback import (
    browser_fallback_response,
    is_gated_platform_error,
)


def test_detects_linkedin_scope_gate() -> None:
    payload = {
        "code": "USER_NOT_AUTHORIZED",
        "message": "Missing permission r_marketing_leadgen_automation",
    }

    assert is_gated_platform_error(403, payload)


def test_ignores_non_auth_platform_error() -> None:
    payload = {"message": "Campaign name is required"}

    assert not is_gated_platform_error(400, payload)


def test_browser_fallback_response_shape() -> None:
    response = browser_fallback_response(
        platform="LinkedIn",
        operation="publish_draft_campaign",
        status_code=403,
        payload={"message": "Application is restricted to vetted partners"},
    )

    assert response["needs_browser_fallback"] is True
    assert response["fallback_tool"] == "browser.run_playwright_flow"
    assert response["risk"] == "credential_sensitive"
    assert response["approval_required"] is True
    assert response["dry_run_required"] is True
    assert "LinkedIn API returned 403" in response["reason"]
