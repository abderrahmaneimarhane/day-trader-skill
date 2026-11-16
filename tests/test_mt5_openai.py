import unittest
from types import SimpleNamespace

from mt5_openai.risk import size_position
from mt5_openai.execution import submit_market_order, ExecutionBlocked


class FakeMT5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self, one_lot_loss=-10.0, min_volume=0.01, step=0.01):
        self.one_lot_loss = one_lot_loss
        self.info = SimpleNamespace(visible=True, volume_min=min_volume,
                                    volume_max=100.0, volume_step=step,
                                    trade_mode=4, filling_mode=1)
    def symbol_info(self, symbol): return self.info
    def symbol_info_tick(self, symbol): return SimpleNamespace(ask=1.1002, bid=1.1000)
    def order_calc_profit(self, kind, symbol, volume, entry, stop):
        return self.one_lot_loss * volume
    def symbol_select(self, symbol, enabled): return True
    def order_check(self, request): return SimpleNamespace(retcode=0)
    def order_send(self, request):
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, _asdict=lambda: {"retcode": 10009})


class RiskTests(unittest.TestCase):
    def test_minimum_volume_over_risk_budget_is_rejected(self):
        mt5 = FakeMT5(one_lot_loss=-100.0, min_volume=0.01)
        decision = size_position(mt5, "EURUSD", mt5.ORDER_TYPE_BUY,
                                  1.1, 1.099, 10.0, 0.02)
        self.assertFalse(decision.approved)
        self.assertIn("minimum volume", decision.reason)

    def test_volume_is_rounded_down_within_two_percent(self):
        mt5 = FakeMT5(one_lot_loss=-10.0, min_volume=0.01)
        decision = size_position(mt5, "EURUSD", mt5.ORDER_TYPE_BUY,
                                  1.1, 1.099, 10.0, 0.02)
        self.assertTrue(decision.approved)
        self.assertEqual(decision.volume, 0.02)
        self.assertLessEqual(decision.estimated_loss, 0.20)

    def test_risk_fraction_cannot_exceed_two_percent(self):
        mt5 = FakeMT5()
        decision = size_position(mt5, "EURUSD", mt5.ORDER_TYPE_BUY,
                                  1.1, 1.099, 10.0, 0.03)
        self.assertFalse(decision.approved)

    def test_paper_mode_never_calls_order_send(self):
        mt5 = FakeMT5()
        decision = SimpleNamespace(approved=True, estimated_loss=0.15)
        account = SimpleNamespace(login=123, server="Exness-MT5", trade_allowed=True)
        result = submit_market_order(mt5, {"execution_mode": "paper", "symbols": ["EURUSD"]},
                                     account, "EURUSD", "buy", 0.01, 1.099, 1.103, decision)
        self.assertEqual(result["status"], "PAPER_PREVIEW")


if __name__ == "__main__":
    unittest.main()
