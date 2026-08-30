import unittest

from backend.routes.paper_trading import router


class PaperTradeRouteTests(unittest.TestCase):
    def test_owned_paper_trade_delete_route_is_available(self):
        paths = {route.path for route in router.routes}
        self.assertIn("/trades/{trade_id}", paths)


if __name__ == "__main__":
    unittest.main()
