import importlib.util
import sys
import threading
import time
import types
import unittest
from decimal import Decimal
from importlib.machinery import SourceFileLoader


TARGET_PATH = "/mnt/d/codex/standx_bot.py"


def load_standx_module():
    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv_module

    websocket_module = types.ModuleType("websocket")

    class DummyWebSocketApp:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def run_forever(self, *args, **kwargs):
            return None

        def send(self, *args, **kwargs):
            return None

        def close(self):
            return None

    websocket_module.WebSocketApp = DummyWebSocketApp
    sys.modules["websocket"] = websocket_module

    requests_module = types.ModuleType("requests")

    class DummyRequestException(Exception):
        pass

    class DummyHTTPError(DummyRequestException):
        def __init__(self, *args, response=None, **kwargs):
            super().__init__(*args)
            self.response = response

    class DummySession:
        def request(self, *args, **kwargs):
            raise AssertionError("network should not be used in unit tests")

    requests_module.RequestException = DummyRequestException
    requests_module.HTTPError = DummyHTTPError
    requests_module.Session = DummySession
    requests_module.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_module

    base58_module = types.ModuleType("base58")
    base58_module.b58encode = lambda value: b"dummy"
    sys.modules["base58"] = base58_module

    nacl_module = types.ModuleType("nacl")
    nacl_signing_module = types.ModuleType("nacl.signing")

    class DummyVerifyKey:
        def encode(self):
            return b"verify-key"

    class DummySigned:
        signature = b"signature"

    class DummySigningKey:
        verify_key = DummyVerifyKey()

        @staticmethod
        def generate():
            return DummySigningKey()

        def sign(self, message):
            return DummySigned()

    nacl_signing_module.SigningKey = DummySigningKey
    sys.modules["nacl"] = nacl_module
    sys.modules["nacl.signing"] = nacl_signing_module

    eth_account_module = types.ModuleType("eth_account")

    class DummySignedMessage:
        def __init__(self):
            self.signature = b"\x00" * 65

    class DummyAccountInstance:
        address = "0x0000000000000000000000000000000000000000"

        def sign_message(self, message):
            return DummySignedMessage()

    class DummyAccount:
        @staticmethod
        def from_key(private_key):
            return DummyAccountInstance()

    eth_account_module.Account = DummyAccount
    sys.modules["eth_account"] = eth_account_module

    eth_account_messages_module = types.ModuleType("eth_account.messages")
    eth_account_messages_module.encode_defunct = lambda text: text
    sys.modules["eth_account.messages"] = eth_account_messages_module

    loader = SourceFileLoader("standx_bot_runtime_guards", TARGET_PATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class RuntimeGuardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_standx_module()

    def build_bot(self):
        bot = self.module.DualSideMakerBot.__new__(self.module.DualSideMakerBot)
        bot.lock = threading.Lock()
        bot.logger = types.SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
        )
        bot.config = types.SimpleNamespace(
            sync_interval_sec=2.0,
            position_sync_interval_sec=2.0,
            symbol="BTC-USD",
            dry_run=False,
            )
        bot.buy_order = None
        bot.sell_order = None
        bot.cached_has_position = False
        bot.last_position_check_ts = 0.0
        bot.last_sync_ts = 0.0
        bot.client = None
        return bot

    def test_success_response_requires_explicit_code(self):
        client = self.module.StandXClient.__new__(self.module.StandXClient)
        self.assertTrue(client.is_success_response({"code": 0}))
        self.assertTrue(client.is_success_response({"code": 200}))
        self.assertFalse(client.is_success_response({"ok": True}))
        self.assertFalse(client.is_success_response({}))

    def test_restored_order_skips_reprice_during_cooldown(self):
        bot = self.build_bot()
        order = self.module.QuoteOrder(
            side="buy",
            cl_ord_id="buy-1",
            price=Decimal("69900"),
            anchor_price=Decimal("70000"),
            placed_ts=time.time() - 60,
            restored_from_sync=True,
            synced_ts=time.time(),
        )

        need_reprice = bot._should_reprice(
            side="buy",
            order=order,
            current_anchor=Decimal("69920"),
            warn_move=Decimal("30"),
            cancel_move=Decimal("60"),
        )

        self.assertFalse(need_reprice)

    def test_has_position_uses_cache_within_sync_interval(self):
        bot = self.build_bot()
        calls = []

        class Client:
            extract_result_list = staticmethod(self.module.StandXClient.extract_result_list)

            def query_positions(self, symbol):
                calls.append(symbol)
                return {"result": [{"qty": "0.01"}]}

        bot.client = Client()

        first = bot._has_position()
        second = bot._has_position()

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(["BTC-USD"], calls)

    def test_cancel_all_forces_sync_when_any_side_fails(self):
        bot = self.build_bot()
        calls = []

        def fake_cancel(side, reason):
            calls.append((side, reason))
            return side == "buy"

        sync_calls = []

        def fake_sync(*, force):
            sync_calls.append(force)

        bot._cancel_side = fake_cancel
        bot._sync_open_orders_if_needed = fake_sync

        bot._cancel_all("test-reason")

        self.assertCountEqual(
            [("buy", "test-reason"), ("sell", "test-reason")],
            calls,
        )
        self.assertEqual([True], sync_calls)

    def test_sync_open_orders_cancels_extra_same_side_orders(self):
        bot = self.build_bot()
        bot.config.order_offset_buy = Decimal("100")
        bot.config.order_offset_sell = Decimal("100")
        canceled_ids = []

        class Client:
            extract_result_list = staticmethod(self.module.StandXClient.extract_result_list)

            def query_open_orders(self, symbol):
                return {
                    "result": [
                        {"side": "buy", "cl_ord_id": "buy-new", "price": "69900", "created_at": "200"},
                        {"side": "buy", "cl_ord_id": "buy-old", "price": "69890", "created_at": "100"},
                        {"side": "sell", "cl_ord_id": "sell-1", "price": "70100", "created_at": "150"},
                    ]
                }

            def cancel_orders(self, ids):
                canceled_ids.extend(ids)
                return {"code": 0}

        bot.client = Client()
        bot._sync_open_orders()

        self.assertIsNotNone(bot.buy_order)
        self.assertEqual("buy-new", bot.buy_order.cl_ord_id)
        self.assertIsNotNone(bot.sell_order)
        self.assertEqual("sell-1", bot.sell_order.cl_ord_id)
        self.assertEqual(["buy-old"], canceled_ids)


class RequestRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_standx_module()

    def build_client(self):
        client = self.module.StandXClient.__new__(self.module.StandXClient)
        client.config = types.SimpleNamespace(
            perps_url="https://perps.standx.com",
            http_max_retries=3,
            http_retry_backoff_sec=0.0,
        )
        client.auth = types.SimpleNamespace(sign_headers=lambda payload: {"x-sign": "ok"})
        client.token = "expired-token"
        client.timeout = (1, 1)
        return client

    def test_request_refreshes_token_once_after_401(self):
        client = self.build_client()
        refreshed = []

        class Response:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload
                self.text = str(payload)

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"http {self.status_code}")

            def json(self):
                return self._payload

        calls = []

        class Session:
            def request(self, **kwargs):
                calls.append(kwargs["headers"]["Authorization"])
                if len(calls) == 1:
                    return Response(401, {"message": "expired"})
                return Response(200, {"code": 0, "result": "ok"})

        client.session = Session()

        def refresh_token():
            refreshed.append(True)
            return "new-token"

        client.refresh_token_cb = refresh_token

        resp = client._request("GET", "/api/query_balance", signed=False)

        self.assertEqual({"code": 0, "result": "ok"}, resp)
        self.assertEqual([True], refreshed)
        self.assertEqual(
            ["Bearer expired-token", "Bearer new-token"],
            calls,
        )

    def test_place_and_cancel_require_explicit_success_code(self):
        module = self.module
        bot = module.DualSideMakerBot.__new__(module.DualSideMakerBot)
        bot.lock = threading.Lock()
        bot.logger = types.SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
        )
        bot.config = types.SimpleNamespace(
            symbol="BTC-USD",
            order_size=Decimal("0.001"),
            leverage=5,
            margin_mode="cross",
            time_in_force="alo",
            dry_run=False,
            max_place_attempts_per_side=20,
        )
        bot.buy_order = None
        bot.buy_place_attempts = 0
        bot.sell_order = module.QuoteOrder(
            side="sell",
            cl_ord_id="sell-1",
            price=Decimal("70100"),
            anchor_price=Decimal("70200"),
            placed_ts=time.time(),
        )
        bot.sell_place_attempts = 1

        class Client:
            @staticmethod
            def is_success_response(resp):
                return isinstance(resp, dict) and resp.get("code") in {0, 200}

            def place_order(self, **kwargs):
                return {"message": "missing code"}

            def cancel_orders(self, ids):
                return {"message": "missing code"}

        bot.client = Client()

        bot._place_side("buy", Decimal("69900"), Decimal("70000"))
        cancel_ok = bot._cancel_side("sell", "test")

        self.assertIsNone(bot.buy_order)
        self.assertFalse(cancel_ok)
        self.assertIsNotNone(bot.sell_order)

    def test_extract_result_list_rejects_invalid_shape(self):
        client = self.module.StandXClient.__new__(self.module.StandXClient)
        with self.assertRaises(RuntimeError):
            client.extract_result_list({"result": {"not": "list"}}, "result")


class DryRunAndCircuitBreakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_standx_module()

    def build_bot(self):
        logs = []

        def push(level):
            return lambda *args, **kwargs: logs.append((level, args))

        bot = self.module.DualSideMakerBot.__new__(self.module.DualSideMakerBot)
        bot.lock = threading.Lock()
        bot.logger = types.SimpleNamespace(info=push("info"), warning=push("warning"), error=push("error"))
        bot.config = types.SimpleNamespace(
            dry_run=True,
            symbol="BTC-USD",
            order_size=Decimal("0.001"),
            leverage=5,
            margin_mode="cross",
            time_in_force="alo",
            max_consecutive_errors=2,
            circuit_breaker_action="stop",
            cancel_move_buy=Decimal("60"),
            cancel_move_sell=Decimal("60"),
            max_place_attempts_per_side=2,
            max_allowed_move_buy=Decimal("0"),
            max_allowed_move_sell=Decimal("0"),
            startup_cancel_stale_orders=True,
        )
        bot.buy_order = None
        bot.sell_order = None
        bot.buy_place_attempts = 0
        bot.sell_place_attempts = 0
        bot.consecutive_error_count = 0
        bot.client = types.SimpleNamespace()
        bot.is_paused = False
        bot._test_logs = logs
        return bot

    def test_place_and_cancel_side_in_dry_run_do_not_call_client(self):
        bot = self.build_bot()

        class Client:
            def place_order(self, **kwargs):
                raise AssertionError("dry run should not call place_order")

            def cancel_orders(self, ids):
                raise AssertionError("dry run should not call cancel_orders")

        bot.client = Client()

        bot._place_side("buy", Decimal("69900"), Decimal("70000"))
        self.assertIsNotNone(bot.buy_order)

        cancel_ok = bot._cancel_side("buy", "dry-run-test")
        self.assertTrue(cancel_ok)
        self.assertIsNone(bot.buy_order)
        self.assertTrue(any("DRY_RUN place side=%s symbol=%s price=%s qty=%s anchor=%s cl_ord_id=%s" == entry[1][0] for entry in bot._test_logs))
        self.assertTrue(any("DRY_RUN cancel side=%s symbol=%s cl_ord_id=%s reason=%s" == entry[1][0] for entry in bot._test_logs))

    def test_handle_runtime_error_triggers_circuit_breaker(self):
        bot = self.build_bot()
        reasons = []

        def fake_cancel_all(reason):
            reasons.append(reason)

        bot._cancel_all = fake_cancel_all

        bot._handle_runtime_error(RuntimeError("boom-1"))
        self.assertEqual(1, bot.consecutive_error_count)

        with self.assertRaises(RuntimeError):
            bot._handle_runtime_error(RuntimeError("boom-2"))

        self.assertEqual(["连续错误熔断"], reasons)

    def test_handle_runtime_error_can_pause(self):
        bot = self.build_bot()
        bot.config.circuit_breaker_action = "pause"
        reasons = []
        bot._cancel_all = lambda reason: reasons.append(reason)

        bot._handle_runtime_error(RuntimeError("boom-1"))
        bot._handle_runtime_error(RuntimeError("boom-2"))

        self.assertTrue(bot.is_paused)
        self.assertEqual(["连续错误熔断"], reasons)

    def test_handle_runtime_error_can_cancel_only(self):
        bot = self.build_bot()
        bot.config.circuit_breaker_action = "cancel-only"
        reasons = []
        bot._cancel_all = lambda reason: reasons.append(reason)

        bot._handle_runtime_error(RuntimeError("boom-1"))
        bot._handle_runtime_error(RuntimeError("boom-2"))

        self.assertFalse(bot.is_paused)
        self.assertEqual(0, bot.consecutive_error_count)
        self.assertEqual(["连续错误熔断"], reasons)

    def test_startup_self_check_skips_external_probe_in_dry_run(self):
        bot = self.build_bot()

        class Client:
            def query_balance(self):
                raise AssertionError("dry run should skip external probe")

        bot.client = Client()
        bot._startup_self_check()

    def test_startup_self_check_rejects_invalid_breaker_action(self):
        bot = self.build_bot()
        bot.config.circuit_breaker_action = "invalid"
        with self.assertRaises(ValueError):
            bot._startup_self_check()

    def test_cleanup_startup_stale_orders_skips_external_cancel_in_dry_run(self):
        bot = self.build_bot()
        calls = []

        class Client:
            extract_result_list = staticmethod(DryRunAndCircuitBreakerTests.module.StandXClient.extract_result_list)

            def query_open_orders(self, symbol):
                calls.append(("query", symbol))
                return {"result": [{"cl_ord_id": "old-1"}, {"cl_ord_id": "old-2"}]}

            def cancel_orders(self, ids):
                raise AssertionError("dry run should not cancel startup stale orders")

        bot.client = Client()
        bot._cleanup_startup_stale_orders()
        self.assertEqual([("query", "BTC-USD")], calls)

    def test_place_side_stops_after_max_attempts(self):
        bot = self.build_bot()
        bot.buy_place_attempts = 2
        with self.assertRaises(RuntimeError):
            bot._place_side("buy", Decimal("69900"), Decimal("70000"))
        self.assertTrue(bot.is_paused)

    def test_max_anchor_move_triggers_protection(self):
        bot = self.build_bot()
        bot.config.max_allowed_move_buy = Decimal("50")
        reasons = []
        bot._cancel_all = lambda reason: reasons.append(reason)
        order = self.module.QuoteOrder(
            side="buy",
            cl_ord_id="buy-1",
            price=Decimal("69900"),
            anchor_price=Decimal("70000"),
            placed_ts=time.time(),
        )

        bot._check_max_anchor_move("buy", order, Decimal("69960"))
        self.assertEqual([], reasons)

        with self.assertRaises(RuntimeError):
            bot._check_max_anchor_move("buy", order, Decimal("69900"))

        self.assertEqual(["buy侧偏移保护触发"], reasons)
        self.assertTrue(bot.is_paused)


if __name__ == "__main__":
    unittest.main()
