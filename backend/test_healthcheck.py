import os
import unittest
from unittest.mock import patch

from backend.healthcheck import probe


class HealthcheckTests(unittest.TestCase):
    def test_public_probe_uses_configured_host(self):
        with patch.dict(os.environ, {"REPLIQUE_PUBLIC_ORIGIN": "https://replique.duckdns.org"}), \
                patch("backend.healthcheck.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            self.assertTrue(probe())
            request = urlopen.call_args.args[0]
            self.assertEqual(request.get_header("Host"), "replique.duckdns.org")

    def test_local_probe_uses_loopback_host(self):
        with patch.dict(os.environ, {"REPLIQUE_PUBLIC_ORIGIN": ""}), \
                patch("backend.healthcheck.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            self.assertTrue(probe())
            request = urlopen.call_args.args[0]
            self.assertEqual(request.get_header("Host"), "127.0.0.1:8000")


if __name__ == "__main__":
    unittest.main()
