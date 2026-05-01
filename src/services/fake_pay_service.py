import aiohttp

class FakePay:
    def __init__(self, settings):
        self.client_session = aiohttp.ClientSession()
        self.fakepay_url = settings.fakepay_url

# FAKE PAY callout here