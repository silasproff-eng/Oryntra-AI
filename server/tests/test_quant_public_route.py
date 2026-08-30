import unittest

from backend.main import app


class QuantPublicRouteTests(unittest.TestCase):
    def test_authenticated_browser_upload_route_is_available_without_public_admin_routes(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/quant/run-upload", paths)


if __name__ == "__main__":
    unittest.main()
