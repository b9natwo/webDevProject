"""
dashboard/src/routers/premium.py — Premium info and Stripe checkout
"""
from fastapi import APIRouter, Depends, HTTPException
from dashboard.src.auth.session import get_current_user
from shared.db.models import User, PremiumTier
from shared.config import get_settings

router = APIRouter(tags=["premium"])


@router.get("/status")
async def premium_status(user: User = Depends(get_current_user)) -> dict:
    return {
        "tier": user.premium_tier.value,
        "expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
    }


@router.post("/checkout/{tier}")
async def create_checkout(
    tier: PremiumTier,
    user: User = Depends(get_current_user),
) -> dict:
    """Create a Stripe checkout session. Returns the checkout URL."""
    settings = get_settings()
    if not settings.stripe_enabled:
        raise HTTPException(status_code=503, detail="Payments not configured")

    if tier == PremiumTier.FREE:
        raise HTTPException(status_code=400, detail="Cannot checkout for Free tier")

    import stripe
    stripe.api_key = settings.stripe_secret_key.get_secret_value()

    price_id = (
        settings.stripe_standard_price_id
        if tier == PremiumTier.STANDARD
        else settings.stripe_pro_price_id
    )
    if not price_id:
        raise HTTPException(status_code=503, detail="Price ID not configured")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.discord_redirect_uri}/premium/success",
        cancel_url=f"{settings.discord_redirect_uri}/premium",
        metadata={"discord_id": str(user.discord_id)},
    )
    return {"checkout_url": session.url}
