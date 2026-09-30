from types import SimpleNamespace

from services.telegram_control import (
    AlertDeduplicator,
    FixedWindowRateLimiter,
    TelegramAuthorizer,
    TelegramControlPlane,
    TelegramPrincipal,
    TelegramRole,
)


def state():
    return SimpleNamespace(
        price=4300,
        positioning_regime="UNKNOWN",
        volatility_regime="UNKNOWN",
        gamma_flip=4280,
        call_wall=4350,
        put_wall=4250,
        gex=12.5,
        oi=1000,
        oi_change=10,
        data_status="VALID",
        data_age_seconds=4,
        data_quality=0.95,
    )


def test_unauthorized_user_is_rejected():
    plane = TelegramControlPlane(TelegramAuthorizer({}))
    response = plane.handle(user_id="1", chat_id="2", command="/gc", market_state=state())
    assert response.text == "UNAUTHORIZED"


def test_authorized_command_returns_market_state_and_buttons():
    principal = TelegramPrincipal("1", "2", TelegramRole.ADMIN)
    plane = TelegramControlPlane(TelegramAuthorizer({("1", "2"): principal}))
    response = plane.handle(user_id="1", chat_id="2", command="/gc", market_state=state())
    assert "Net GEX: 12.5" in response.text
    assert response.buttons


def test_unknown_and_trading_commands_are_disabled():
    principal = TelegramPrincipal("1", "2", TelegramRole.ADMIN)
    plane = TelegramControlPlane(TelegramAuthorizer({("1", "2"): principal}))
    assert plane.handle(user_id="1", chat_id="2", command="/trade", market_state=state()).text == "COMMAND_DISABLED"


def test_rate_limit_and_dedup():
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)
    principal = TelegramPrincipal("1", "2", TelegramRole.ADMIN)
    plane = TelegramControlPlane(
        TelegramAuthorizer({("1", "2"): principal}),
        rate_limiter=limiter,
    )
    assert plane.handle(user_id="1", chat_id="2", command="/status", market_state=state()).text.startswith("STATUS")
    assert plane.handle(user_id="1", chat_id="2", command="/status", market_state=state()).text == "RATE_LIMITED"

    dedup = AlertDeduplicator(cooldown_seconds=60)
    assert dedup.allow("same", now=100)
    assert not dedup.allow("same", now=120)
