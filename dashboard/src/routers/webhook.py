from fastapi import APIRouter, Request, HTTPException
import stripe
from shared.config import get_settings
from shared.db.session import get_db_session
from shared.db.repositories.user_repo import UserRepository

router = APIRouter(prefix="/webhook")

@router.post("/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    settings = get_settings()

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    if event["type"] == "customer.subscription.created" or event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await handle_subscription_change(subscription)

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await handle_subscription_canceled(subscription)

    return {"status": "success"}


async def handle_subscription_change(subscription):
    async with get_db_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_stripe_customer_id(subscription["customer"])
        if user:
            tier = map_stripe_price_to_tier(subscription["items"]["data"][0]["price"]["id"])
            user.premium_tier = tier
            await session.commit()


def map_stripe_price_to_tier(price_id: str):
    settings = get_settings()
    if price_id == settings.stripe_supporter_price_id:
        return "supporter"
    elif price_id == settings.stripe_premium_price_id:
        return "premium"
    return "free"
