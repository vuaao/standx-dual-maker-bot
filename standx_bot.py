#!/usr/bin/env python3
import argparse
import json
import logging
import os
import threading
import time
import uuid
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Optional, Tuple

try:
    import base58
    import requests
    import websocket
    from dotenv import load_dotenv
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from nacl.signing import SigningKey
except ModuleNotFoundError as exc:
    missing_module = exc.name or "unknown"
    raise SystemExit(
        f"缺少依赖模块: {missing_module}。请先执行 `pip install -r requirements.txt`。"
    ) from exc


load_dotenv()


def env_str(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise ValueError(f"{name} 未设置")
    return value


def env_decimal(name: str, default: str) -> Decimal:
    raw = os.getenv(name, default)
    try:
        return Decimal(raw)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{name} 不是合法数字: {raw}") from exc


def env_float(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 不是合法浮点数: {raw}") from exc


def env_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 不是合法整数: {raw}") from exc


def env_bool(name: str, default: str) -> bool:
    value = os.getenv(name, default)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_api_timestamp(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts >= 1e14:
            return ts / 1_000_000.0
        if ts >= 1e11:
            return ts / 1_000.0
        return ts
    if isinstance(value, str):
        text = value.strip()
        if text.replace(".", "", 1).isdigit():
            return parse_api_timestamp(float(text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def mask_address(value: str) -> str:
    if not value or len(value) < 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


@dataclass
class BotConfig:
    wallet_private_key: str
    wallet_address: str
    chain: str
    symbol: str
    order_size: Decimal
    order_offset_buy: Decimal
    order_offset_sell: Decimal
    warn_move_buy: Decimal
    warn_move_sell: Decimal
    cancel_move_buy: Decimal
    cancel_move_sell: Decimal
    max_allowed_move_buy: Decimal
    max_allowed_move_sell: Decimal
    max_order_age_sec: float
    max_place_attempts_per_side: int
    min_gap: Decimal
    leverage: int
    margin_mode: str
    time_in_force: str
    main_loop_interval: float
    sync_interval_sec: float
    position_sync_interval_sec: float
    max_market_age_sec: float
    dry_run: bool
    pause_on_position: bool
    sync_cancel_both_sides: bool
    max_consecutive_errors: int
    circuit_breaker_action: str
    startup_cancel_stale_orders: bool
    base_api_url: str
    perps_url: str
    market_ws_url: str
    http_connect_timeout: float
    http_read_timeout: float
    http_max_retries: int
    http_retry_backoff_sec: float
    auth_max_retries: int
    log_level: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        return cls(
            wallet_private_key=env_str("WALLET_PRIVATE_KEY"),
            wallet_address=env_str("WALLET_ADDRESS"),
            chain=os.getenv("CHAIN", "bsc").lower(),
            symbol=os.getenv("SYMBOL", "BTC-USD"),
            order_size=env_decimal("ORDER_SIZE", "0.001"),
            order_offset_buy=env_decimal("ORDER_OFFSET_BUY", "100"),
            order_offset_sell=env_decimal("ORDER_OFFSET_SELL", "100"),
            warn_move_buy=env_decimal("WARN_MOVE_BUY", "30"),
            warn_move_sell=env_decimal("WARN_MOVE_SELL", "30"),
            cancel_move_buy=env_decimal("CANCEL_MOVE_BUY", "60"),
            cancel_move_sell=env_decimal("CANCEL_MOVE_SELL", "60"),
            max_allowed_move_buy=env_decimal("MAX_ALLOWED_MOVE_BUY", "0"),
            max_allowed_move_sell=env_decimal("MAX_ALLOWED_MOVE_SELL", "0"),
            max_order_age_sec=env_float("MAX_ORDER_AGE_SEC", "20"),
            max_place_attempts_per_side=env_int("MAX_PLACE_ATTEMPTS_PER_SIDE", "20"),
            min_gap=env_decimal("MIN_GAP", "1"),
            leverage=env_int("LEVERAGE", "5"),
            margin_mode=os.getenv("MARGIN_MODE", "cross"),
            time_in_force=os.getenv("TIME_IN_FORCE", "alo").lower(),
            main_loop_interval=env_float("MAIN_LOOP_INTERVAL", "0.5"),
            sync_interval_sec=env_float("SYNC_INTERVAL_SEC", "2"),
            position_sync_interval_sec=env_float("POSITION_SYNC_INTERVAL_SEC", "2"),
            max_market_age_sec=env_float("MAX_MARKET_AGE_SEC", "3"),
            dry_run=env_bool("DRY_RUN", "false"),
            pause_on_position=env_bool("PAUSE_ON_POSITION", "true"),
            sync_cancel_both_sides=env_bool("SYNC_CANCEL_BOTH_SIDES", "true"),
            max_consecutive_errors=env_int("MAX_CONSECUTIVE_ERRORS", "5"),
            circuit_breaker_action=os.getenv("CIRCUIT_BREAKER_ACTION", "stop").strip().lower(),
            startup_cancel_stale_orders=env_bool("STARTUP_CANCEL_STALE_ORDERS", "true"),
            base_api_url=os.getenv("BASE_API_URL", "https://api.standx.com"),
            perps_url=os.getenv("PERPS_URL", "https://perps.standx.com"),
            market_ws_url=os.getenv("MARKET_WS_URL", "wss://perps.standx.com/ws-stream/v1"),
            http_connect_timeout=env_float("HTTP_CONNECT_TIMEOUT", "3"),
            http_read_timeout=env_float("HTTP_READ_TIMEOUT", "10"),
            http_max_retries=env_int("HTTP_MAX_RETRIES", "3"),
            http_retry_backoff_sec=env_float("HTTP_RETRY_BACKOFF_SEC", "0.5"),
            auth_max_retries=env_int("AUTH_MAX_RETRIES", "3"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


@dataclass
class QuoteOrder:
    side: str
    cl_ord_id: str
    price: Decimal
    anchor_price: Decimal
    placed_ts: float
    warned: bool = False
    restored_from_sync: bool = False
    synced_ts: float = 0.0


@dataclass
class MarketState:
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    updated_ts: float = 0.0


class StandXAuth:
    def __init__(self, base_api_url: str):
        self.base_api_url = base_api_url.rstrip("/")
        self.ed25519_signer = SigningKey.generate()
        self.request_id = base58.b58encode(self.ed25519_signer.verify_key.encode()).decode()

    def authenticate(
        self,
        *,
        chain: str,
        wallet_address: str,
        sign_message,
        timeout: Tuple[float, float],
        expires_seconds: int = 604800,
    ) -> Dict[str, Any]:
        prepare_url = f"{self.base_api_url}/v1/offchain/prepare-signin?chain={chain}"
        prepare_resp = requests.post(
            prepare_url,
            json={"address": wallet_address, "requestId": self.request_id},
            timeout=timeout,
        )
        prepare_resp.raise_for_status()
        prepare_data = prepare_resp.json()
        if not prepare_data.get("success") or not prepare_data.get("signedData"):
            raise RuntimeError(f"prepare-signin 失败: {prepare_data}")

        signed_data = prepare_data["signedData"]
        payload = self._parse_jwt_payload(signed_data)
        signature = sign_message(payload["message"])

        login_url = f"{self.base_api_url}/v1/offchain/login?chain={chain}"
        login_resp = requests.post(
            login_url,
            json={
                "signature": signature,
                "signedData": signed_data,
                "expiresSeconds": expires_seconds,
            },
            timeout=timeout,
        )
        login_resp.raise_for_status()
        login_data = login_resp.json()
        if not login_data.get("token"):
            raise RuntimeError(f"login 失败: {login_data}")
        return login_data

    def sign_headers(self, payload_text: str) -> Dict[str, str]:
        request_id = str(uuid.uuid4())
        timestamp = str(int(time.time() * 1000))
        version = "v1"
        message = f"{version},{request_id},{timestamp},{payload_text}".encode("utf-8")
        signature = self.ed25519_signer.sign(message).signature
        return {
            "x-request-sign-version": version,
            "x-request-id": request_id,
            "x-request-timestamp": timestamp,
            "x-request-signature": base64.b64encode(signature).decode("utf-8"),
        }

    @staticmethod
    def _parse_jwt_payload(token: str) -> Dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("signedData 不是合法 JWT")
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = json.loads(
            __import__("base64").urlsafe_b64decode(payload + padding).decode("utf-8")
        )
        return decoded


class WalletSigner:
    def __init__(self, private_key: str):
        self.account = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return self.account.address

    def sign_message(self, message: str) -> str:
        signed = self.account.sign_message(encode_defunct(text=message))
        return "0x" + signed.signature.hex()


class StandXClient:
    def __init__(
        self,
        config: BotConfig,
        auth: StandXAuth,
        token: str,
        refresh_token_cb: Optional[Callable[[], str]] = None,
    ):
        self.config = config
        self.auth = auth
        self.token = token
        self.refresh_token_cb = refresh_token_cb
        self.session = requests.Session()
        self.timeout = (config.http_connect_timeout, config.http_read_timeout)

    def query_open_orders(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", "/api/query_open_orders", params={"symbol": symbol}, signed=False)

    def query_positions(self, symbol: str) -> Any:
        return self._request("GET", "/api/query_positions", params={"symbol": symbol}, signed=False)

    def query_balance(self) -> Dict[str, Any]:
        return self._request("GET", "/api/query_balance", signed=False)

    def change_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/change_leverage",
            payload={"symbol": symbol, "leverage": leverage},
            signed=True,
        )

    def change_margin_mode(self, symbol: str, margin_mode: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/change_margin_mode",
            payload={"symbol": symbol, "margin_mode": margin_mode},
            signed=True,
        )

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        leverage: int,
        margin_mode: str,
        time_in_force: str,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "symbol": symbol,
            "side": side,
            "order_type": "limit",
            "qty": self._fmt(qty),
            "price": self._fmt(price),
            "time_in_force": time_in_force,
            "reduce_only": reduce_only,
            "margin_mode": margin_mode,
            "leverage": leverage,
            "cl_ord_id": cl_ord_id or str(uuid.uuid4()),
        }
        return self._request("POST", "/api/new_order", payload=payload, signed=True)

    def cancel_orders(self, cl_ord_ids: list[str]) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/cancel_orders",
            payload={"cl_ord_id_list": cl_ord_ids},
            signed=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        signed: bool,
    ) -> Dict[str, Any]:
        url = self.config.perps_url.rstrip("/") + path
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":"))
        last_error: Optional[Exception] = None
        refreshed = False

        for attempt in range(1, self.config.http_max_retries + 1):
            headers = {"Authorization": f"Bearer {self.token}"}
            if data is not None:
                headers["Content-Type"] = "application/json"
                if signed:
                    headers.update(self.auth.sign_headers(data))

            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    data=data,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.config.http_max_retries:
                    break
                time.sleep(self.config.http_retry_backoff_sec * attempt)
                continue

            if response.status_code == 401 and self.refresh_token_cb and not refreshed:
                refreshed = True
                self.token = self.refresh_token_cb()
                continue

            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = requests.HTTPError(
                    f"{method} {path} 返回 {response.status_code}: {response.text[:300]}",
                    response=response,
                )
                if attempt >= self.config.http_max_retries:
                    break
                time.sleep(self.config.http_retry_backoff_sec * attempt)
                continue

            response.raise_for_status()
            return response.json()

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{method} {path} 请求失败，未拿到有效响应")

    @staticmethod
    def is_success_response(resp: Dict[str, Any]) -> bool:
        return isinstance(resp, dict) and resp.get("code") in {0, 200}

    @staticmethod
    def extract_result_list(resp: Any, field_name: str) -> list[Dict[str, Any]]:
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            result = resp.get(field_name, resp.get("result"))
            if isinstance(result, list):
                return result
        raise RuntimeError(f"响应结构异常，期望 list 字段，实际={resp}")

    @staticmethod
    def require_dict(resp: Any, context: str) -> Dict[str, Any]:
        if isinstance(resp, dict):
            return resp
        raise RuntimeError(f"{context} 响应结构异常，期望 dict，实际={resp}")

    @staticmethod
    def _fmt(value: Decimal) -> str:
        return format(value.normalize(), "f")


class MarketStream:
    def __init__(self, ws_url: str, symbol: str, logger: logging.Logger):
        self.ws_url = ws_url
        self.symbol = symbol
        self.logger = logger
        self.state = MarketState()
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.ws: Optional[websocket.WebSocketApp] = None

    def start(self):
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if self.ws is not None:
            self.ws.close()
        if self.thread is not None:
            self.thread.join(timeout=3)

    def snapshot(self) -> MarketState:
        with self.lock:
            return MarketState(
                best_bid=self.state.best_bid,
                best_ask=self.state.best_ask,
                updated_ts=self.state.updated_ts,
            )

    def _run_forever(self):
        while not self._stop_event.is_set():
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self.ws.run_forever(ping_interval=20, ping_timeout=10)
            if not self._stop_event.is_set():
                time.sleep(2)

    def _on_open(self, ws):
        subscribe = {"subscribe": {"channel": "depth_book", "symbol": self.symbol}}
        ws.send(json.dumps(subscribe))
        self.logger.info("已订阅 depth_book: %s", self.symbol)

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if data.get("channel") != "depth_book":
            return
        book = data.get("data") or {}
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            return
        try:
            best_bid = max(Decimal(row[0]) for row in bids)
            best_ask = min(Decimal(row[0]) for row in asks)
        except (InvalidOperation, IndexError, TypeError):
            return
        with self.lock:
            self.state.best_bid = best_bid
            self.state.best_ask = best_ask
            self.state.updated_ts = time.time()

    def _on_error(self, ws, error):
        self.logger.warning("行情 WS 异常: %s", error)

    def _on_close(self, ws, code, msg):
        self.logger.warning("行情 WS 断开 code=%s msg=%s", code, msg)


class DualSideMakerBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.logger = logging.getLogger("standx_dual_maker")
        self.logger.setLevel(getattr(logging, config.log_level, logging.INFO))
        self.logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(handler)
        logging.getLogger("websocket").setLevel(logging.WARNING)

        self.wallet = WalletSigner(config.wallet_private_key)
        if self.wallet.address.lower() != config.wallet_address.lower():
            raise ValueError(
                f"WALLET_ADDRESS 不匹配，env={mask_address(config.wallet_address)} 实际={mask_address(self.wallet.address)}"
            )
        self.config.wallet_private_key = ""

        self.auth = StandXAuth(config.base_api_url)
        self.token: Optional[str] = None
        self.client: Optional[StandXClient] = None
        self.market = MarketStream(config.market_ws_url, config.symbol, self.logger)
        self.lock = threading.Lock()
        self.buy_order: Optional[QuoteOrder] = None
        self.sell_order: Optional[QuoteOrder] = None
        self.buy_place_attempts = 0
        self.sell_place_attempts = 0
        self.last_sync_ts = 0.0
        self.cached_has_position = False
        self.last_position_check_ts = 0.0
        self.consecutive_error_count = 0
        self.is_paused = False

    def run(self):
        self._authenticate()
        self._startup_self_check()
        self._cleanup_startup_stale_orders()
        self._init_account()
        self.market.start()
        self.logger.info(
            "机器人启动，交易对=%s dry_run=%s breaker_action=%s",
            self.config.symbol,
            self.config.dry_run,
            self.config.circuit_breaker_action,
        )

        try:
            while True:
                try:
                    if self.is_paused:
                        time.sleep(self.config.main_loop_interval)
                        continue
                    self._loop_once()
                    self.consecutive_error_count = 0
                except Exception as exc:
                    self._handle_runtime_error(exc)
                time.sleep(self.config.main_loop_interval)
        except KeyboardInterrupt:
            self.logger.info("收到停止信号，开始撤单")
        finally:
            self._cancel_all("退出脚本")
            self.market.stop()

    def run_self_check(self):
        self._authenticate()
        self._startup_self_check()
        self.logger.info("self-check 完成，可以开始部署或试运行")

    def _authenticate(self):
        self.logger.info("开始认证")
        last_error: Optional[Exception] = None
        for attempt in range(1, self.config.auth_max_retries + 1):
            try:
                login = self.auth.authenticate(
                    chain=self.config.chain,
                    wallet_address=self.config.wallet_address,
                    sign_message=self.wallet.sign_message,
                    timeout=(self.config.http_connect_timeout, self.config.http_read_timeout),
                )
                self.token = login["token"]
                if self.client is None:
                    self.client = StandXClient(
                        self.config,
                        self.auth,
                        self.token,
                        refresh_token_cb=self._refresh_token,
                    )
                else:
                    self.client.token = self.token
                self.logger.info("认证成功，地址=%s", login.get("address"))
                return
            except Exception as exc:
                last_error = exc
                if attempt >= self.config.auth_max_retries:
                    break
                self.logger.warning("认证失败，准备重试 attempt=%s error=%s", attempt, exc)
                time.sleep(self.config.http_retry_backoff_sec * attempt)

        if last_error is not None:
            raise last_error
        raise RuntimeError("认证失败，未拿到 token")

    def _refresh_token(self) -> str:
        self.logger.warning("检测到 token 失效，开始重新认证")
        self._authenticate()
        if not self.token:
            raise RuntimeError("重新认证后仍未拿到 token")
        return self.token

    def _init_account(self):
        assert self.client is not None
        if self.config.dry_run:
            self.logger.info("DRY_RUN=true，跳过账户初始化写操作")
            return
        leverage_resp = self.client.change_leverage(self.config.symbol, self.config.leverage)
        margin_resp = self.client.change_margin_mode(self.config.symbol, self.config.margin_mode)
        balance_resp = self.client.query_balance()
        self.client.require_dict(balance_resp, "query_balance")
        self.logger.info(
            "账户初始化完成 leverage=%s margin_mode=%s balance=%s",
            leverage_resp.get("code"),
            margin_resp.get("code"),
            balance_resp.get("balance"),
        )

    def _startup_self_check(self):
        assert self.client is not None
        breaker_action = self.config.circuit_breaker_action
        if breaker_action not in {"stop", "pause", "cancel-only"}:
            raise ValueError(f"CIRCUIT_BREAKER_ACTION 不支持: {breaker_action}")

        self.logger.info(
            "启动自检 symbol=%s dry_run=%s time_in_force=%s",
            self.config.symbol,
            self.config.dry_run,
            self.config.time_in_force,
        )
        if self.config.order_size <= 0:
            raise ValueError("ORDER_SIZE 必须大于 0")
        if self.config.cancel_move_buy <= 0 or self.config.cancel_move_sell <= 0:
            raise ValueError("CANCEL_MOVE 必须大于 0")
        if self.config.max_consecutive_errors <= 0:
            raise ValueError("MAX_CONSECUTIVE_ERRORS 必须大于 0")
        if self.config.max_place_attempts_per_side <= 0:
            raise ValueError("MAX_PLACE_ATTEMPTS_PER_SIDE 必须大于 0")

        if self.config.dry_run:
            self.logger.info("启动自检通过：DRY_RUN 模式，跳过外部接口探测")
            return

        balance_resp = self.client.query_balance()
        balance_data = self.client.require_dict(balance_resp, "startup query_balance")
        self.logger.info("启动自检通过：余额接口可用 balance=%s", balance_data.get("balance"))

    def _cleanup_startup_stale_orders(self):
        assert self.client is not None
        if not self.config.startup_cancel_stale_orders:
            return
        resp = self.client.query_open_orders(self.config.symbol)
        orders = self.client.extract_result_list(resp, "result")
        stale_ids = [str(row.get("cl_ord_id")) for row in orders if row.get("cl_ord_id")]
        if not stale_ids:
            return
        if self.config.dry_run:
            self.logger.info("DRY_RUN startup cleanup symbol=%s ids=%s", self.config.symbol, stale_ids)
            return
        self.logger.warning("启动清理历史遗留订单 symbol=%s ids=%s", self.config.symbol, stale_ids)
        cancel_resp = self.client.cancel_orders(stale_ids)
        if not self.client.is_success_response(cancel_resp):
            raise RuntimeError(f"启动清理遗留订单失败: {cancel_resp}")

    def _handle_runtime_error(self, exc: Exception):
        self.consecutive_error_count += 1
        self.logger.warning(
            "主循环异常 consecutive=%s/%s error=%s",
            self.consecutive_error_count,
            self.config.max_consecutive_errors,
            exc,
        )
        if self.consecutive_error_count >= self.config.max_consecutive_errors:
            action = self.config.circuit_breaker_action
            self.logger.error("连续错误达到上限，执行熔断 action=%s", action)
            self._cancel_all("连续错误熔断")
            if action == "pause":
                self.is_paused = True
                self.logger.error("熔断动作：已暂停运行，等待人工介入")
                return
            if action == "cancel-only":
                self.logger.error("熔断动作：已撤单，继续保活观察")
                self.consecutive_error_count = 0
                return
            raise RuntimeError("连续错误熔断触发") from exc

    def _loop_once(self):
        self._sync_open_orders_if_needed(force=False)

        market = self.market.snapshot()
        if not market.best_bid or not market.best_ask:
            return
        if market.best_ask <= market.best_bid:
            self.logger.warning("盘口异常，ask<=bid，跳过本轮")
            return
        if time.time() - market.updated_ts > self.config.max_market_age_sec:
            self.logger.warning("行情超时，先撤单等待恢复")
            self._cancel_all("行情超时")
            return

        if self.config.pause_on_position and self._has_position():
            self.logger.warning("检测到持仓，暂停挂单并撤掉现有订单")
            self._cancel_all("检测到持仓")
            return

        current_buy_anchor = market.best_bid
        current_sell_anchor = market.best_ask

        with self.lock:
            buy_order = self.buy_order
            sell_order = self.sell_order

        self._check_max_anchor_move("buy", buy_order, current_buy_anchor)
        self._check_max_anchor_move("sell", sell_order, current_sell_anchor)

        need_buy_reprice = self._should_reprice(
            side="buy",
            order=buy_order,
            current_anchor=current_buy_anchor,
            warn_move=self.config.warn_move_buy,
            cancel_move=self.config.cancel_move_buy,
        )
        need_sell_reprice = self._should_reprice(
            side="sell",
            order=sell_order,
            current_anchor=current_sell_anchor,
            warn_move=self.config.warn_move_sell,
            cancel_move=self.config.cancel_move_sell,
        )

        if need_buy_reprice or need_sell_reprice:
            if self.config.sync_cancel_both_sides:
                self._cancel_all("一侧达到重挂阈值，双边同步撤单")
            else:
                if need_buy_reprice:
                    self._cancel_side("buy", "买侧达到重挂阈值")
                if need_sell_reprice:
                    self._cancel_side("sell", "卖侧达到重挂阈值")
            self._sync_open_orders_if_needed(force=True)
            with self.lock:
                buy_order = self.buy_order
                sell_order = self.sell_order

        if buy_order is None:
            buy_price = min(
                current_buy_anchor - self.config.order_offset_buy,
                market.best_ask - self.config.min_gap,
            )
            self._place_side("buy", buy_price, current_buy_anchor)

        if sell_order is None:
            sell_price = max(
                current_sell_anchor + self.config.order_offset_sell,
                market.best_bid + self.config.min_gap,
            )
            self._place_side("sell", sell_price, current_sell_anchor)

    def _sync_open_orders_if_needed(self, *, force: bool):
        if not force and time.time() - self.last_sync_ts < self.config.sync_interval_sec:
            return
        self.last_sync_ts = time.time()
        self._sync_open_orders()

    def _sync_open_orders(self):
        assert self.client is not None
        resp = self.client.query_open_orders(self.config.symbol)
        orders = self.client.extract_result_list(resp, "result")

        with self.lock:
            local_buy = self.buy_order
            local_sell = self.sell_order

        buy_rows = [row for row in orders if str(row.get("side", "")).lower() == "buy"]
        sell_rows = [row for row in orders if str(row.get("side", "")).lower() == "sell"]
        buy_row, extra_buy_ids = self._pick_primary_order(buy_rows)
        sell_row, extra_sell_ids = self._pick_primary_order(sell_rows)

        buy = self._build_quote_order(buy_row, local_buy, self.config.order_offset_buy)
        sell = self._build_quote_order(sell_row, local_sell, self.config.order_offset_sell)

        with self.lock:
            self.buy_order = buy
            self.sell_order = sell

        extra_ids = extra_buy_ids + extra_sell_ids
        if extra_ids:
            self.logger.warning("发现同方向多单，准备撤掉多余订单 ids=%s", extra_ids)
            try:
                if self.config.dry_run:
                    self.logger.info("DRY_RUN cancel_extras symbol=%s ids=%s", self.config.symbol, extra_ids)
                    return
                self.client.cancel_orders(extra_ids)
            except Exception as exc:
                self.logger.warning("撤多余订单失败 ids=%s error=%s", extra_ids, exc)

    def _pick_primary_order(self, rows: list[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], list[str]]:
        if not rows:
            return None, []
        sorted_rows = sorted(
            rows,
            key=lambda row: parse_api_timestamp(row.get("created_at") or row.get("timestamp")),
            reverse=True,
        )
        primary = sorted_rows[0]
        extras = [str(row.get("cl_ord_id")) for row in sorted_rows[1:] if row.get("cl_ord_id")]
        return primary, extras

    def _build_quote_order(
        self,
        row: Optional[Dict[str, Any]],
        local_order: Optional[QuoteOrder],
        offset: Decimal,
    ) -> Optional[QuoteOrder]:
        if row is None:
            return None
        price = Decimal(str(row["price"]))
        placed_ts = parse_api_timestamp(row.get("created_at") or row.get("timestamp")) or time.time()
        side = str(row["side"]).lower()
        if local_order and local_order.cl_ord_id == row.get("cl_ord_id"):
            anchor_price = local_order.anchor_price
            warned = local_order.warned
        else:
            anchor_price = price + offset if side == "buy" else price - offset
            warned = False
        return QuoteOrder(
            side=side,
            cl_ord_id=str(row["cl_ord_id"]),
            price=price,
            anchor_price=anchor_price,
            placed_ts=placed_ts,
            warned=warned,
            restored_from_sync=not (local_order and local_order.cl_ord_id == row.get("cl_ord_id")),
            synced_ts=time.time(),
        )

    def _should_reprice(
        self,
        *,
        side: str,
        order: Optional[QuoteOrder],
        current_anchor: Decimal,
        warn_move: Decimal,
        cancel_move: Decimal,
    ) -> bool:
        if order is None:
            return False

        move = abs(current_anchor - order.anchor_price)
        age = time.time() - order.placed_ts
        if order.restored_from_sync and (time.time() - order.synced_ts) < self.config.sync_interval_sec:
            return False

        if not order.warned and warn_move > 0 and move >= warn_move and move < cancel_move:
            order.warned = True
            self.logger.warning(
                "%s 侧触发预警，锚点偏移=%s，当前锚点=%s，挂单价=%s",
                side,
                move,
                current_anchor,
                order.price,
            )
        if order.warned and move < warn_move:
            order.warned = False

        if move >= cancel_move:
            self.logger.info("%s 侧达到撤单阈值，偏移=%s", side, move)
            return True
        if age >= self.config.max_order_age_sec:
            self.logger.info("%s 侧达到超时重挂阈值，订单年龄=%.1fs", side, age)
            return True
        return False

    def _check_max_anchor_move(
        self,
        side: str,
        order: Optional[QuoteOrder],
        current_anchor: Decimal,
    ):
        if order is None:
            return
        max_allowed_move = (
            self.config.max_allowed_move_buy if side == "buy" else self.config.max_allowed_move_sell
        )
        if max_allowed_move <= 0:
            return
        move = abs(current_anchor - order.anchor_price)
        if move > max_allowed_move:
            self.logger.error(
                "%s 侧偏移超过保护阈值 move=%s threshold=%s，执行保护性撤单并暂停",
                side,
                move,
                max_allowed_move,
            )
            self._cancel_all(f"{side}侧偏移保护触发")
            self.is_paused = True
            raise RuntimeError(f"{side} side max move protection triggered")

    def _place_side(self, side: str, price: Decimal, anchor_price: Decimal):
        assert self.client is not None
        current_attempts = self.buy_place_attempts if side == "buy" else self.sell_place_attempts
        if current_attempts >= self.config.max_place_attempts_per_side:
            self.logger.error(
                "%s 侧挂单次数达到上限 attempts=%s limit=%s，停止该侧继续挂单",
                side,
                current_attempts,
                self.config.max_place_attempts_per_side,
            )
            self.is_paused = True
            raise RuntimeError(f"{side} side place attempts exceeded")
        cl_ord_id = str(uuid.uuid4())
        if self.config.dry_run:
            order = QuoteOrder(
                side=side,
                cl_ord_id=cl_ord_id,
                price=price,
                anchor_price=anchor_price,
                placed_ts=time.time(),
            )
            with self.lock:
                if side == "buy":
                    self.buy_order = order
                    self.buy_place_attempts += 1
                else:
                    self.sell_order = order
                    self.sell_place_attempts += 1
            self.logger.info(
                "DRY_RUN place side=%s symbol=%s price=%s qty=%s anchor=%s cl_ord_id=%s",
                side,
                self.config.symbol,
                price,
                self.config.order_size,
                anchor_price,
                cl_ord_id,
            )
            return
        resp = self.client.place_order(
            symbol=self.config.symbol,
            side=side,
            qty=self.config.order_size,
            price=price,
            leverage=self.config.leverage,
            margin_mode=self.config.margin_mode,
            time_in_force=self.config.time_in_force,
            cl_ord_id=cl_ord_id,
        )
        if not self.client.is_success_response(resp):
            self.logger.warning("%s 挂单失败: %s", side, resp)
            return

        order = QuoteOrder(
            side=side,
            cl_ord_id=cl_ord_id,
            price=price,
            anchor_price=anchor_price,
            placed_ts=time.time(),
        )
        with self.lock:
            if side == "buy":
                self.buy_order = order
                self.buy_place_attempts += 1
            else:
                self.sell_order = order
                self.sell_place_attempts += 1
        self.logger.info("%s 挂单成功 price=%s anchor=%s", side, price, anchor_price)

    def _cancel_side(self, side: str, reason: str):
        assert self.client is not None
        with self.lock:
            order = self.buy_order if side == "buy" else self.sell_order
        if order is None:
            return True
        if self.config.dry_run:
            with self.lock:
                if side == "buy":
                    self.buy_order = None
                    self.buy_place_attempts = 0
                else:
                    self.sell_order = None
                    self.sell_place_attempts = 0
            self.logger.info(
                "DRY_RUN cancel side=%s symbol=%s cl_ord_id=%s reason=%s",
                side,
                self.config.symbol,
                order.cl_ord_id,
                reason,
            )
            return True
        resp = self.client.cancel_orders([order.cl_ord_id])
        if not self.client.is_success_response(resp):
            self.logger.warning(
                "%s 撤单失败 cl_ord_id=%s reason=%s resp=%s",
                side,
                order.cl_ord_id,
                reason,
                resp,
            )
            return False
        with self.lock:
            if side == "buy":
                self.buy_order = None
                self.buy_place_attempts = 0
            else:
                self.sell_order = None
                self.sell_place_attempts = 0
        self.logger.info("%s 撤单成功 cl_ord_id=%s reason=%s", side, order.cl_ord_id, reason)
        return True

    def _cancel_all(self, reason: str):
        with ThreadPoolExecutor(max_workers=2) as pool:
            buy_future = pool.submit(self._cancel_side, "buy", reason)
            sell_future = pool.submit(self._cancel_side, "sell", reason)
            buy_ok = buy_future.result()
            sell_ok = sell_future.result()
        if not buy_ok or not sell_ok:
            self._sync_open_orders_if_needed(force=True)

    def _has_position(self) -> bool:
        assert self.client is not None
        if self.config.dry_run:
            return False
        now = time.time()
        if now - self.last_position_check_ts < self.config.position_sync_interval_sec:
            return self.cached_has_position

        resp = self.client.query_positions(self.config.symbol)
        positions = self.client.extract_result_list(resp, "result")
        has_position = False
        for row in positions or []:
            try:
                qty = Decimal(str(row.get("qty", "0")))
            except InvalidOperation:
                continue
            if qty != 0:
                has_position = True
                break
        self.cached_has_position = has_position
        self.last_position_check_ts = now
        return has_position


def main():
    parser = argparse.ArgumentParser(description="StandX dual-side maker bot")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="只执行认证和启动自检，不进入主循环",
    )
    args = parser.parse_args()

    config = BotConfig.from_env()
    bot = DualSideMakerBot(config)
    if args.self_check:
        bot.run_self_check()
        return
    bot.run()


if __name__ == "__main__":
    main()
