import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import quota_testing


class QuotaTestingTests(unittest.TestCase):
    def test_quota_test_deadline_expires_and_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "quota-test.json"
            with patch.object(quota_testing, "TEST_STATE", state), patch.object(quota_testing.time, "time", return_value=1000):
                deadline = quota_testing.set_quota_test(60)
                self.assertEqual(deadline, 1060)
                with patch.object(quota_testing.time, "time", return_value=1030):
                    self.assertEqual(quota_testing.quota_test_remaining(), 30)
                with patch.object(quota_testing.time, "time", return_value=1061):
                    self.assertEqual(quota_testing.quota_test_remaining(), 0)
                self.assertFalse(state.exists())

    def test_quota_test_invalid_duration_rejected(self):
        with self.assertRaises(ValueError):
            quota_testing.set_quota_test(0)


if __name__ == "__main__":
    unittest.main()
