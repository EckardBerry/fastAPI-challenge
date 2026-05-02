import aiohttp

from src.models.card import Card
from src.models.fake_pay import FakePayRequest


class FakePay:
    """Service for authorizing payments via FakePay."""
    def __init__(self, settings):
        self.client_session = aiohttp.ClientSession()
        self.fakepay_url = settings.fakepay_url

    async def authorize_payment(self, amount, transaction_id: str, card: Card) -> bool:
        """POST to FakePay; returns True only on HTTP 200."""
        try:
            payload = FakePayRequest(
                transaction_id=transaction_id,
                card=card,
            ).model_dump(mode="json", by_alias=True)
            async with self.client_session.post(
                self.fakepay_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False