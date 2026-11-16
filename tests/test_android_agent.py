import unittest
from mt5_openai.android_agent import set_decision


class AndroidApprovalTests(unittest.TestCase):
    def test_approval_is_only_manual_review(self):
        proposal = {"status": "pending"}
        result = set_decision(proposal, "approved_for_manual_review")
        self.assertEqual(result["status"], "approved_for_manual_review")
        self.assertNotIn("order_ticket", result)
        self.assertNotIn("order_send", result)

    def test_reject_proposal(self):
        proposal = {"status": "pending"}
        self.assertEqual(set_decision(proposal, "rejected")["status"], "rejected")

    def test_cannot_decide_twice(self):
        proposal = {"status": "pending"}
        set_decision(proposal, "rejected")
        with self.assertRaises(ValueError):
            set_decision(proposal, "approved_for_manual_review")

    def test_only_supported_decisions(self):
        with self.assertRaises(ValueError):
            set_decision({"status": "pending"}, "execute_live")


if __name__ == "__main__":
    unittest.main()
