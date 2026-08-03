import os
import json
import ssl
import time
import logging
import threading
import configparser
import dataclasses
from typing import Any, Dict, List, Optional, Tuple, Generator
from dataclasses import dataclass, field, fields
from urllib.request import Request, urlopen, URLError

logger = logging.getLogger("zabbix_service")


class ZabbixBaseError(Exception):
    def __init__(self, message: str, http_status: int = None, raw_response: str = None,
                 request_method: str = None):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.raw_response = raw_response
        self.request_method = request_method

    def __str__(self):
        parts = [self.message]
        if self.http_status is not None:
            parts.append(f"[HTTP {self.http_status}]")
        if self.request_method:
            parts.append(f"(method={self.request_method})")
        return " ".join(parts)


class ZabbixConnectionError(ZabbixBaseError):
    pass


class ZabbixAuthenticationError(ZabbixBaseError):
    pass


class ZabbixAPIError(ZabbixBaseError):
    def __init__(self, message: str, code: int = None, api_data: Any = None,
                 http_status: int = None, raw_response: str = None, request_method: str = None):
        super().__init__(message, http_status=http_status, raw_response=raw_response,
                         request_method=request_method)
        self.code = code
        self.api_data = api_data

    def __str__(self):
        parts = [f"Zabbix API error {self.code}: {self.message}"] if self.code else [self.message]
        if self.http_status is not None:
            parts.append(f"[HTTP {self.http_status}]")
        if self.request_method:
            parts.append(f"(method={self.request_method})")
        return " ".join(parts)


class ZabbixValidationError(ZabbixBaseError):
    pass


@dataclass
class HostInfo:
    hostid: str
    host: str
    name: str
    status: int = 0
    ip: str = ""
    groups: List[Dict[str, Any]] = field(default_factory=list)
    templates: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "HostInfo":
        groups = d.get("groups") or []
        templates = d.get("parentTemplates") or []
        interfaces = d.get("interfaces") or []
        ip = ""
        if interfaces:
            ip = interfaces[0].get("ip", "")
        return cls(
            hostid=d["hostid"],
            host=d["host"],
            name=d.get("name", d["host"]),
            status=int(d.get("status", 0)),
            ip=ip,
            groups=groups,
            templates=templates,
        )


@dataclass
class HostInterface:
    interfaceid: str
    hostid: str
    type: int = 1
    ip: str = ""
    dns: str = ""
    port: str = ""
    main: int = 0
    description: str = ""
    useip: int = 1

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "HostInterface":
        desc = d.get("description", "")
        if not desc and isinstance(d.get("details"), dict):
            desc = d["details"].get("description", "")
        return cls(
            interfaceid=d["interfaceid"],
            hostid=d.get("hostid", ""),
            type=int(d.get("type", 1)),
            ip=d.get("ip", ""),
            dns=d.get("dns", ""),
            port=d.get("port", ""),
            main=int(d.get("main", 0)),
            description=desc,
            useip=int(d.get("useip", 1)),
        )


@dataclass
class GroupInfo:
    groupid: str
    name: str
    internal: int = 0

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "GroupInfo":
        return cls(
            groupid=d["groupid"],
            name=d.get("name", ""),
            internal=int(d.get("internal", 0)),
        )


@dataclass
class InterfaceMatch:
    host: HostInfo
    interface: HostInterface
    match_field: str = "description"

    @property
    def matched_value(self) -> str:
        return getattr(self.interface, self.match_field, "")


@dataclass
class ProblemInfo:
    eventid: str
    objectid: str
    name: str
    severity: int = 0
    clock: int = 0
    acknowledged: bool = False
    host: str = ""

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "ProblemInfo":
        return cls(
            eventid=d["eventid"],
            objectid=d.get("objectid", ""),
            name=d.get("name", ""),
            severity=int(d.get("severity", 0)),
            clock=int(d.get("clock", 0)),
            acknowledged=bool(int(d.get("acknowledged", 0))),
            host=d.get("host", ""),
        )


@dataclass
class HistoryRecord:
    itemid: str
    clock: int
    value: str
    ns: int = 0

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "HistoryRecord":
        return cls(
            itemid=d["itemid"],
            clock=int(d.get("clock", 0)),
            value=d.get("value", ""),
            ns=int(d.get("ns", 0)),
        )


@dataclass
class ScriptResult:
    response: int
    value: str

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "ScriptResult":
        return cls(
            response=int(d.get("response", 0)),
            value=d.get("value", ""),
        )


@dataclass
class HostFilter:
    group: Optional[str] = None
    search_name: Optional[str] = None
    status: Optional[int] = None
    tags: Optional[List[Dict[str, str]]] = None


@dataclass
class HostCreateRequest:
    host: str
    name: str
    groups: List[Dict[str, str]]
    interfaces: List[Dict[str, Any]]
    templates: Optional[List[Dict[str, str]]] = None
    macros: Optional[List[Dict[str, str]]] = None

    def __post_init__(self):
        if not self.host:
            raise ZabbixValidationError("host is required")
        if not self.groups:
            raise ZabbixValidationError("at least one group is required")
        if not self.interfaces:
            raise ZabbixValidationError("at least one interface is required")


@dataclass
class TriggerEvent:
    eventid: str
    objectid: str
    clock: int
    value: int
    name: str
    severity: int

    @classmethod
    def from_zabbix_dict(cls, d: dict) -> "TriggerEvent":
        return cls(
            eventid=d["eventid"],
            objectid=d.get("objectid", ""),
            clock=int(d.get("clock", 0)),
            value=int(d.get("value", 0)),
            name=d.get("name", ""),
            severity=int(d.get("severity", 0)),
        )


@dataclass
class ZabbixConfig:
    url: str = ""
    token: str = ""
    user: str = ""
    password: str = ""
    verify_ssl: bool = True
    timeout: int = 120
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retryable_statuses: Tuple[int, ...] = (429, 500, 502, 503, 504)

    @classmethod
    def from_dict(cls, d: dict) -> "ZabbixConfig":
        known = {f.name: f.type for f in fields(cls)}
        kwargs = {}
        for k, v in d.items():
            if k not in known:
                continue
            field_type = known[k]

            if k == "verify_ssl":
                if isinstance(v, str):
                    kwargs[k] = v.lower() in ("true", "1", "yes")
                else:
                    kwargs[k] = bool(v)
                continue

            if v is None or v == "":
                continue

            if field_type is int or field_type == int:
                kwargs[k] = int(v)
            elif field_type is float or field_type == float:
                kwargs[k] = float(v)
            elif field_type is bool or field_type == bool:
                if isinstance(v, str):
                    kwargs[k] = v.lower() in ("true", "1", "yes")
                else:
                    kwargs[k] = bool(v)
            elif field_type == Tuple[int, ...] or getattr(field_type, "__origin__", None) is tuple:
                if isinstance(v, str):
                    kwargs[k] = tuple(int(x.strip()) for x in v.split(",") if x.strip())
                elif isinstance(v, (list, tuple)):
                    kwargs[k] = tuple(int(x) if not isinstance(x, int) else x for x in v)
                else:
                    kwargs[k] = v
            else:
                kwargs[k] = v

        return cls(**kwargs)

    @classmethod
    def from_ini(cls, path: str) -> "ZabbixConfig":
        cp = configparser.ConfigParser()
        cp.read(path)
        d = {}
        if cp.has_section("zabbix"):
            for k, v in cp["zabbix"].items():
                d[k] = v
        return cls.from_dict(d)

    @classmethod
    def from_env(cls) -> "ZabbixConfig":
        mapping = {
            "ZABBIX_URL": "url",
            "ZABBIX_TOKEN": "token",
            "ZABBIX_USER": "user",
            "ZABBIX_PASSWORD": "password",
            "ZABBIX_VERIFY_SSL": "verify_ssl",
            "ZABBIX_TIMEOUT": "timeout",
            "ZABBIX_MAX_RETRIES": "max_retries",
            "ZABBIX_RETRY_BASE_DELAY": "retry_base_delay",
            "ZABBIX_RETRYABLE_STATUSES": "retryable_statuses",
        }
        d = {}
        for env_key, config_key in mapping.items():
            val = os.environ.get(env_key)
            if val is not None:
                if config_key == "retryable_statuses":
                    d[config_key] = [int(x.strip()) for x in val.split(",") if x.strip()]
                else:
                    d[config_key] = val
        return cls.from_dict(d)

    @classmethod
    def resolve(cls, ini_path: str = None, overrides: dict = None) -> "ZabbixConfig":
        config = cls()

        if overrides:
            config = cls.from_dict(overrides)

        if ini_path and os.path.isfile(ini_path):
            ini_cfg = cls.from_ini(ini_path)
            config = cls._apply(config, ini_cfg)

        env_cfg = cls.from_env()
        config = cls._apply(config, env_cfg)

        return config

    @staticmethod
    def _apply(base: "ZabbixConfig", overlay: "ZabbixConfig") -> "ZabbixConfig":
        result = {}
        for f in fields(base):
            overlay_val = getattr(overlay, f.name)
            base_val = getattr(base, f.name)
            default_val = f.default if f.default is not dataclasses.MISSING else None
            if isinstance(default_val, dataclasses.Field):
                default_val = None
            if default_val is not None or overlay_val is not None:
                zero_for_type = (
                    "" if isinstance(overlay_val, str) else
                    0 if isinstance(overlay_val, int) else
                    0.0 if isinstance(overlay_val, float) else
                    () if isinstance(overlay_val, tuple) else
                    None
                )
                if overlay_val == zero_for_type or overlay_val == default_val:
                    result[f.name] = base_val
                else:
                    result[f.name] = overlay_val
            else:
                result[f.name] = overlay_val if overlay_val is not None else base_val
        return ZabbixConfig.from_dict(result)


class _ZabbixClient:
    def __init__(self, config: ZabbixConfig):
        self._config = config
        self._request_id = 0
        self._id_lock = threading.Lock()
        self._auth_token: Optional[str] = None
        self._auth_lock = threading.Lock()
        self._logged_in = False

        if config.token:
            self._auth_token = config.token
        elif config.user and config.password:
            self._auth_token = None
        else:
            raise ZabbixValidationError(
                "Either 'token' or ('user' + 'password') must be provided"
            )

        self._ssl_ctx = self._build_ssl_context()

    @staticmethod
    def _classify_api_error(err: dict, http_status: int, raw_response: str,
                            request_method: str) -> ZabbixAPIError:
        code = err.get("code")
        msg = err.get("message", "Unknown API error")
        msg_lower = msg.lower()
        is_auth = (
            (code == -32602 and ("password" in msg_lower or "login" in msg_lower))
            or code == -32500
        )
        if is_auth:
            return ZabbixAuthenticationError(
                message=msg,
                http_status=http_status,
                raw_response=raw_response,
                request_method=request_method,
            )
        return ZabbixAPIError(
            message=msg,
            code=code,
            api_data=err.get("data"),
            http_status=http_status,
            raw_response=raw_response,
            request_method=request_method,
        )

    def _build_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if not self._config.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _next_id(self) -> int:
        with self._id_lock:
            self._request_id += 1
            return self._request_id

    def _mask_token(self, text: str) -> str:
        token = self._config.token or self._auth_token or ""
        if token and len(token) >= 8:
            masked = token[:4] + "*" * (len(token) - 8) + token[-4:]
            text = text.replace(token, masked)
        elif token:
            text = text.replace(token, "****")
        return text

    def _mask_payload(self, payload_str: str) -> str:
        for sensitive in ("token", "password", "auth", "user"):
            marker = f'"{sensitive}": "'
            idx = payload_str.find(marker)
            if idx == -1:
                continue
            start = idx + len(marker)
            end = payload_str.find('"', start)
            if end > start:
                val = payload_str[start:end]
                if sensitive == "user" and len(val) > 0:
                    payload_str = payload_str[:start] + val + payload_str[end:]
                    continue
                masked = val[:4] + "****" if len(val) > 4 else "****"
                payload_str = payload_str[:start] + masked + payload_str[end:]
        return payload_str

    def _ensure_authenticated(self):
        with self._auth_lock:
            if self._logged_in:
                return
            if self._config.token:
                self._auth_token = self._config.token
                self._logged_in = True
                return
            if not self._config.user or not self._config.password:
                raise ZabbixValidationError("No authentication method available")
            logger.info("Logging into Zabbix as user '%s'", self._config.user)
            payload = {
                "jsonrpc": "2.0",
                "method": "user.login",
                "params": {
                    "user": self._config.user,
                    "password": self._config.password,
                },
                "id": self._next_id(),
            }
            try:
                result = self._send_payload(payload)
            except ZabbixAPIError as e:
                raise ZabbixAuthenticationError(
                    message=f"Login failed: {e.message}",
                    http_status=e.http_status,
                    raw_response=e.raw_response,
                    request_method="user.login",
                ) from e
            self._auth_token = result
            self._logged_in = True
            logger.info("Zabbix login successful")

    def _send_payload(self, payload: dict) -> Any:
        url = self._config.url
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json-rpc"},
            method="POST",
        )

        last_exc = None
        start = None
        raw = None

        for attempt in range(1, self._config.max_retries + 2):
            try:
                start = time.monotonic()
                resp = urlopen(
                    req,
                    timeout=self._config.timeout,
                    context=self._ssl_ctx,
                )
                elapsed = time.monotonic() - start
                raw = resp.read().decode("utf-8")
                status = resp.status

                logger.debug(
                    "Zabbix request: %s | response time: %.3fs | status: %d",
                    self._mask_payload(json.dumps(payload)), elapsed, status,
                )

                data = json.loads(raw)

                if "error" in data:
                    err = data["error"]
                    exc = self._classify_api_error(
                        err, status, raw, payload.get("method"),
                    )
                    raise exc

                return data.get("result")

            except URLError as e:
                status = getattr(e, "code", None) or getattr(e.reason, "errno", None)
                logger.warning(
                    "Zabbix connection error (attempt %d/%d): %s",
                    attempt, self._config.max_retries + 1, e,
                )
                if isinstance(e.reason, ssl.SSLError):
                    raise ZabbixConnectionError(
                        f"SSL error: {e.reason}",
                        http_status=status,
                        request_method=payload.get("method"),
                    ) from e

                if isinstance(e.reason, TimeoutError):
                    exc = ZabbixConnectionError(
                        f"Timeout after {self._config.timeout}s",
                        request_method=payload.get("method"),
                    )
                else:
                    exc = ZabbixConnectionError(
                        f"Connection error: {e.reason}",
                        http_status=status,
                        raw_response=str(e.reason),
                        request_method=payload.get("method"),
                    )

                if status in self._config.retryable_statuses and attempt <= self._config.max_retries:
                    delay = self._config.retry_base_delay * (2 ** (attempt - 1))
                    logger.warning("Retrying in %.2fs (attempt %d)", delay, attempt)
                    time.sleep(delay)
                    last_exc = exc
                    continue

                raise exc from e

            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ZabbixAPIError(
                    message=f"Invalid JSON response: {e}",
                    raw_response=raw,
                    request_method=payload.get("method"),
                ) from e

            except ZabbixAPIError:
                raise

            except TimeoutError as e:
                logger.warning(
                    "Zabbix request timeout (attempt %d/%d): %s",
                    attempt, self._config.max_retries + 1, e,
                )
                exc = ZabbixConnectionError(
                    f"Timeout after {self._config.timeout}s",
                    request_method=payload.get("method"),
                )
                if attempt <= self._config.max_retries:
                    delay = self._config.retry_base_delay * (2 ** (attempt - 1))
                    logger.warning("Retrying in %.2fs (attempt %d)", delay, attempt)
                    time.sleep(delay)
                    last_exc = exc
                    continue
                raise exc from e

            except Exception as e:
                raise ZabbixBaseError(
                    message=f"Unexpected error: {e}",
                    request_method=payload.get("method"),
                ) from e

        if last_exc:
            raise last_exc

    def request(self, method: str, params: dict = None) -> Any:
        if method not in ("user.login", "user.logout", "apiinfo.version"):
            try:
                self._ensure_authenticated()
            except ZabbixAuthenticationError:
                raise
            except ZabbixAPIError as e:
                if e.code == -32602 or (e.message and ("authentication" in e.message.lower()
                                                        or "session" in e.message.lower()
                                                        or "permission" in e.message.lower())):
                    raise ZabbixAuthenticationError(
                        message=e.message,
                        http_status=e.http_status,
                        raw_response=e.raw_response,
                        request_method=method,
                    ) from e
                raise

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_id(),
        }

        if self._auth_token and method not in ("user.login", "apiinfo.version"):
            payload["auth"] = self._auth_token

        logger.info("Zabbix API call: %s", method)
        print(f"[ZABBIX] Calling {method} with params: {self._mask_params(method, params)}")
        response_data = self._send_payload(payload)
        print(f"[ZABBIX] Response for {method}: {json.dumps(response_data)[:200] if response_data else 'None'}")
        return response_data

    def batch_request(self, calls: List[Tuple[str, dict]]) -> List[Any]:
        try:
            self._ensure_authenticated()
        except ZabbixAuthenticationError:
            raise
        except ZabbixAPIError as e:
            if e.code == -32602 or (e.message and ("authentication" in e.message.lower()
                                                    or "session" in e.message.lower()
                                                    or "permission" in e.message.lower())):
                raise ZabbixAuthenticationError(
                    message=e.message,
                    http_status=e.http_status,
                    raw_response=e.raw_response,
                    request_method="batch",
                ) from e
            raise

        payloads = []
        for method, params in calls:
            p = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
                "id": self._next_id(),
            }
            if self._auth_token:
                p["auth"] = self._auth_token
            payloads.append(p)
            logger.info(
                "Zabbix batch call: %s | params: %s",
                method, self._mask_params(method, params),
            )

        if not payloads:
            return []

        body = json.dumps(payloads).encode("utf-8")
        url = self._config.url
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json-rpc"},
            method="POST",
        )

        last_exc = None
        for attempt in range(1, self._config.max_retries + 2):
            try:
                start = time.monotonic()
                resp = urlopen(req, timeout=self._config.timeout, context=self._ssl_ctx)
                elapsed = time.monotonic() - start
                raw = resp.read().decode("utf-8")
                status = resp.status

                logger.debug(
                    "Zabbix batch request (%d calls) | response time: %.3fs | status: %d",
                    len(payloads), elapsed, status,
                )

                results = json.loads(raw)
                if not isinstance(results, list):
                    raise ZabbixAPIError(
                        message="Expected list response for batch request",
                        raw_response=raw,
                    )

                out = []
                for item in results:
                    if "error" in item:
                        err = item["error"]
                        raise ZabbixAPIError(
                            message=err.get("message", "Batch API error"),
                            code=err.get("code"),
                            api_data=err.get("data"),
                            http_status=status,
                            raw_response=raw,
                        )
                    out.append(item.get("result"))
                return out

            except URLError as e:
                status = getattr(e, "code", None) or getattr(e.reason, "errno", None)
                logger.warning(
                    "Zabbix batch connection error (attempt %d/%d): %s",
                    attempt, self._config.max_retries + 1, e,
                )
                if isinstance(e.reason, ssl.SSLError):
                    raise ZabbixConnectionError(f"SSL error: {e.reason}") from e

                exc = ZabbixConnectionError(
                    f"Batch connection error: {e.reason}",
                    http_status=status,
                    raw_response=str(e.reason),
                )

                if status in self._config.retryable_statuses and attempt <= self._config.max_retries:
                    delay = self._config.retry_base_delay * (2 ** (attempt - 1))
                    logger.warning("Retrying batch in %.2fs (attempt %d)", delay, attempt)
                    time.sleep(delay)
                    last_exc = exc
                    continue

                raise exc from e

            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ZabbixAPIError(message=f"Invalid JSON in batch response: {e}") from e

            except ZabbixAPIError:
                raise

            except TimeoutError as e:
                logger.warning(
                    "Zabbix batch request timeout (attempt %d/%d): %s",
                    attempt, self._config.max_retries + 1, e,
                )
                exc = ZabbixConnectionError(
                    f"Batch timeout after {self._config.timeout}s",
                    request_method="batch",
                )
                if attempt <= self._config.max_retries:
                    delay = self._config.retry_base_delay * (2 ** (attempt - 1))
                    logger.warning("Retrying batch in %.2fs (attempt %d)", delay, attempt)
                    time.sleep(delay)
                    last_exc = exc
                    continue
                raise exc from e

            except Exception as e:
                raise ZabbixBaseError(message=f"Unexpected batch error: {e}") from e

        if last_exc:
            raise last_exc

    def _mask_params(self, method: str, params: dict = None) -> str:
        if not params:
            return "{}"
        masked = {}
        for k, v in params.items():
            if k in ("password", "token", "auth"):
                masked[k] = "****"
            else:
                masked[k] = v
        text = json.dumps(masked)
        return self._mask_token(text)

    def logout(self):
        if not self._logged_in:
            return
        try:
            if self._config.user and not self._config.token:
                logger.info("Logging out from Zabbix")
                self.request("user.logout")
        except Exception:
            logger.warning("Zabbix logout failed (ignored)")
        finally:
            with self._auth_lock:
                self._auth_token = None
                self._logged_in = False

    @property
    def config(self) -> ZabbixConfig:
        return self._config


class ZabbixService:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    @classmethod
    def reset_singleton(cls):
        with cls._instance_lock:
            cls._instance = None

    def __init__(self, config: ZabbixConfig = None):
        if getattr(self, "_initialized", False):
            return
        if config is None:
            raise ZabbixValidationError("config is required on first init")
        self._client = _ZabbixClient(config)
        self._config = config
        self._initialized = True

    def __del__(self):
        try:
            if hasattr(self, "_client"):
                self._client.logout()
        except Exception:
            pass

    def close(self):
        if hasattr(self, "_client"):
            self._client.logout()

    @property
    def config(self) -> ZabbixConfig:
        return self._config

    # ------------------------------------------------------------------
    # Low-level generic
    # ------------------------------------------------------------------

    def request(self, method: str, params: dict = None) -> Any:
        return self._client.request(method, params)

    def batch_request(self, calls: List[Tuple[str, dict]]) -> List[Any]:
        return self._client.batch_request(calls)

    # ------------------------------------------------------------------
    # Hosts
    # ------------------------------------------------------------------

    def get_hosts(self, host_filter: HostFilter = None) -> List[HostInfo]:
        params = {
            "output": ["hostid", "host", "name", "status"],
            "selectGroups": ["groupid", "name"],
            "selectParentTemplates": ["templateid", "name"],
            "selectInterfaces": ["ip"],
        }

        if host_filter:
            if host_filter.group:
                params["groupids"] = host_filter.group
            if host_filter.search_name:
                params["search"] = {"name": host_filter.search_name}
                params["searchByAny"] = True
            if host_filter.status is not None:
                params["filter"] = {"status": str(host_filter.status)}
            if host_filter.tags:
                params["tags"] = host_filter.tags

        raw = self.request("host.get", params)
        if not raw:
            return []
        return [HostInfo.from_zabbix_dict(h) for h in raw]

    def get_host_by_name(self, name: str) -> Optional[HostInfo]:
        hosts = self.get_hosts(HostFilter(search_name=name))
        for h in hosts:
            if h.name == name or h.host == name:
                return h
        return None

    def add_host(self, host_data: HostCreateRequest) -> str:
        if isinstance(host_data, dict):
            host_data = HostCreateRequest(**host_data)
        params = {
            "host": host_data.host,
            "name": host_data.name,
            "groups": host_data.groups,
            "interfaces": host_data.interfaces,
        }
        if host_data.templates:
            params["templates"] = host_data.templates
        if host_data.macros:
            params["macros"] = host_data.macros

        result = self.request("host.create", params)
        if result and "hostids" in result:
            return result["hostids"][0]
        raise ZabbixAPIError("host.create did not return hostids")

    def update_host(self, hostid: str, updates: dict) -> bool:
        params = {"hostid": hostid}
        params.update(updates)
        self.request("host.update", params)
        return True

    def delete_host(self, hostid: str) -> bool:
        self.request("host.delete", [hostid])
        return True

    def enable_host(self, hostid: str) -> bool:
        return self.update_host(hostid, {"status": "0"})

    def disable_host(self, hostid: str) -> bool:
        return self.update_host(hostid, {"status": "1"})

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def get_groups(self, name: str = None) -> List[GroupInfo]:
        params = {
            "output": ["groupid", "name"],
        }
        if name:
            params["filter"] = {"name": [name]}
        raw = self.request("hostgroup.get", params)
        if not raw:
            return []
        return [GroupInfo.from_zabbix_dict(g) for g in raw]

    def get_group_by_name(self, name: str) -> Optional[GroupInfo]:
        groups = self.get_groups(name=name)
        for g in groups:
            if g.name == name:
                return g
        return None

    # ------------------------------------------------------------------
    # Interfaces
    # ------------------------------------------------------------------

    def get_host_interfaces(self, hostids: List[str] = None) -> List[HostInterface]:
        params = {
            "output": [
                "interfaceid", "hostid", "type", "ip", "dns",
                "port", "main", "useip", "description",
            ],
        }
        if hostids:
            params["hostids"] = hostids
        raw = self.request("hostinterface.get", params)
        if not raw:
            return []
        return [HostInterface.from_zabbix_dict(i) for i in raw]

    # ------------------------------------------------------------------
    # Interface Description Search
    # ------------------------------------------------------------------

    def search_interface_descriptions(
        self,
        group_name: str,
        search_term: str,
        case_sensitive: bool = False,
        partial: bool = True,
    ) -> List[InterfaceMatch]:
        group = self.get_group_by_name(group_name)
        if not group:
            logger.warning("Group '%s' not found", group_name)
            return []

        hosts = self.get_hosts(HostFilter(group=group.groupid))
        if not hosts:
            return []

        hostids = [h.hostid for h in hosts]
        interfaces = self.get_host_interfaces(hostids)

        host_map = {h.hostid: h for h in hosts}

        matches: List[InterfaceMatch] = []
        for iface in interfaces:
            desc = iface.description
            if not desc:
                continue
            if not case_sensitive:
                desc = desc.lower()
                term = search_term.lower()
            else:
                term = search_term
            if (partial and term in desc) or (not partial and desc == term):
                host = host_map.get(iface.hostid)
                if host:
                    matches.append(InterfaceMatch(host=host, interface=iface))

        return matches

    def find_hosts_by_interface_description(
        self,
        group_name: str,
        search_term: str,
        case_sensitive: bool = False,
        partial: bool = True,
    ) -> List[HostInfo]:
        matches = self.search_interface_descriptions(
            group_name, search_term, case_sensitive, partial,
        )
        seen = set()
        result = []
        for m in matches:
            if m.host.hostid not in seen:
                seen.add(m.host.hostid)
                result.append(m.host)
        return result

    def export_group_data(self, group_name: str) -> List[dict]:
        group = self.get_group_by_name(group_name)
        if not group:
            logger.warning("Group '%s' not found", group_name)
            return []

        params = {
            "output": ["hostid", "host", "name", "status"],
            "groupids": group.groupid,
            "selectGroups": ["groupid", "name"],
            "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type", "main", "useip"],
            "selectDetails": ["description"],
        }
        raw_hosts = self.request("host.get", params)
        if not raw_hosts:
            return []

        result = []
        for h in raw_hosts:
            interfaces_raw = h.get("interfaces") or []
            interfaces = []
            for iface in interfaces_raw:
                details = iface.get("details") or {}
                description = ""
                if isinstance(details, dict):
                    description = details.get("description", "")
                interfaces.append({
                    "interfaceid": iface.get("interfaceid", ""),
                    "ip": iface.get("ip", ""),
                    "dns": iface.get("dns", ""),
                    "port": iface.get("port", ""),
                    "type": int(iface.get("type", 1)),
                    "description": description,
                })
            groups = h.get("groups") or []
            result.append({
                "hostid": h["hostid"],
                "host": h["host"],
                "name": h.get("name", h["host"]),
                "status": int(h.get("status", 0)),
                "groups": [{"groupid": g["groupid"], "name": g["name"]} for g in groups],
                "interfaces": interfaces,
            })
        return result

    def search_group_data(
        self,
        group_name: str,
        search_term: str,
        search_host_name: bool = True,
        search_host_visible_name: bool = True,
        search_interface_description: bool = True,
        search_host_items: bool = True,
        case_sensitive: bool = False,
        partial: bool = True,
    ) -> List[dict]:
        group = self.get_group_by_name(group_name)
        if not group:
            logger.warning("Group '%s' not found", group_name)
            return []

        data = self.export_group_data(group_name)
        hostids = [entry["hostid"] for entry in data]

        item_map = {}
        if search_host_items and hostids:
            item_params = {
                "output": ["itemid", "hostid", "name", "key_"],
                "hostids": hostids,
                "search": {
                    "name": ["Interface ", "interface "],
                },
                "searchByAny": True,
                "sortfield": ["name"],
                "sortorder": "ASC",
                "limit": 5000,
            }
            try:
                raw_items = self.request("item.get", item_params)
                if raw_items:
                    for item in raw_items:
                        hid = item.get("hostid")
                        if hid not in item_map:
                            item_map[hid] = []
                        item_map[hid].append({
                            "itemid": item["itemid"],
                            "name": item.get("name", ""),
                            "key_": item.get("key_", ""),
                        })
            except Exception:
                logger.warning("Failed to query host items", exc_info=True)

        if not case_sensitive:
            term = search_term.lower()
        else:
            term = search_term

        results = []
        for entry in data:
            matched = False
            match_fields = {}

            if search_host_name:
                val = entry["host"]
                if not case_sensitive:
                    val = val.lower()
                if (partial and term in val) or (not partial and val == term):
                    match_fields["host"] = entry["host"]
                    matched = True

            if search_host_visible_name and not matched:
                val = entry["name"]
                if not case_sensitive:
                    val = val.lower()
                if (partial and term in val) or (not partial and val == term):
                    match_fields["name"] = entry["name"]
                    matched = True

            if search_interface_description and not matched:
                for iface in entry["interfaces"]:
                    val = iface["description"]
                    if not val:
                        continue
                    if not case_sensitive:
                        val = val.lower()
                    if (partial and term in val) or (not partial and val == term):
                        match_fields["interface_description"] = iface["description"]
                        match_fields["interface_ip"] = iface["ip"]
                        matched = True
                        break

            if search_host_items and not matched:
                hid = entry["hostid"]
                host_items = item_map.get(hid, [])
                for item in host_items:
                    name_val = item["name"]
                    if not name_val:
                        continue
                    check = name_val.lower() if not case_sensitive else name_val
                    t = term.lower() if not case_sensitive else term
                    if (partial and t in check) or (not partial and check == t):
                        match_fields["item_name"] = name_val
                        match_fields["item_key"] = item["key_"]
                        matched = True
                        break

            if matched:
                results.append({
                    **entry,
                    "matched_fields": match_fields,
                })

        return results

    # ------------------------------------------------------------------
    # Local Database (weekly-refreshed JSON cache)
    # ------------------------------------------------------------------

    def refresh_router_db(self, group_name: str, db_path: str, batch_size: int = 10) -> dict:
        import re

        group = self.get_group_by_name(group_name)
        if not group:
            raise ZabbixValidationError(f"Group '{group_name}' not found")

        group_hostids = self.request("host.get", {
            "output": ["hostid"],
            "groupids": group.groupid,
        })
        if not group_hostids:
            raise ZabbixValidationError(f"No hosts found in group '{group_name}'")

        all_hostids = [h["hostid"] for h in group_hostids]
        logger.info("Processing %d routers in batches of %d", len(all_hostids), batch_size)

        db = {
            "group": {
                "groupid": group.groupid,
                "name": group.name,
            },
            "refreshed_at": int(time.time()),
            "refreshed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "routers": [],
            "summary": {},
        }

        total_items = 0
        iface_pattern = re.compile(r"Interface\s+([^(]+)\(([^)]*)\)")
        total_hosts = len(all_hostids)

        # Load existing DB or create a new one
        existing_db = None
        if os.path.exists(db_path):
            with open(db_path, "r", encoding="utf-8") as f:
                existing_db = json.load(f)
            # Filter out existing entries for the current group
            existing_routers = [
                r for r in existing_db.get("routers", [])
                if not any(g.get("name") == group_name for g in r.get("groups", []))
            ]
            db["routers"].extend(existing_routers)
        else:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        def _write_progress():
            progress = {
                "processed": len(db["routers"]),
                "total": total_hosts,
                "percent": round(len(db["routers"]) / total_hosts * 100, 1) if total_hosts else 100,
            }
            db["_progress"] = progress
            has_existing_routers = existing_db and existing_db.get("routers")
            if db["routers"] or has_existing_routers:
                with open(db_path, "w", encoding="utf-8") as f:
                    json.dump(db, f, indent=2, ensure_ascii=False)
            db.pop("_progress", None)

        for batch_start in range(0, len(all_hostids), batch_size):
            batch_ids = all_hostids[batch_start:batch_start + batch_size]
            logger.info(
                "Batch %d-%d (%d hosts, %d/%d processed)",
                batch_start + 1, batch_start + len(batch_ids),
                len(batch_ids), len(db["routers"]), total_hosts,
            )

            batch_hosts = self.request("host.get", {
                "output": ["hostid", "host", "name", "status"],
                "hostids": batch_ids,
                "selectInterfaces": [
                    "interfaceid", "hostid", "type", "ip", "dns",
                    "port", "main", "useip", "description",
                ],
            })
            if not batch_hosts:
                continue

            # Only fetch items if batch is small enough (<50 hosts)
            batch_items = []
            if len(batch_ids) <= 100:
                batch_items = self.request("item.get", {
                    "output": [
                        "itemid", "hostid", "name", "key_",
                        "value_type", "units", "lastvalue", "lastclock",
                    ],
                    "hostids": batch_ids,
                    "search": {"name": ["Interface "]},
                    "searchByAny": True,
                    "limit": 5000,
                }) or []
            else:
                logger.warning("Skipping item.get for batch of %d hosts (too large)", len(batch_ids))

            items_by_host: Dict[str, List[dict]] = {}
            for item in batch_items:
                hid = item["hostid"]
                if hid not in items_by_host:
                    items_by_host[hid] = []
                m = iface_pattern.search(item["name"])
                iface_name = ""
                iface_desc = ""
                if m:
                    iface_name = m.group(1).strip()
                    iface_desc = m.group(2).strip()
                items_by_host[hid].append({
                    "itemid": item["itemid"],
                    "name": item["name"],
                    "key_": item.get("key_", ""),
                    "value_type": int(item.get("value_type", 0)),
                    "units": item.get("units", ""),
                    "lastvalue": item.get("lastvalue", ""),
                    "lastclock": int(item.get("lastclock", 0)),
                    "interface_name": iface_name,
                    "interface_description": iface_desc,
                })

            router_map = {r["hostid"]: r for r in db["routers"]}
            for h in batch_hosts:
                hid = h["hostid"]
                host_items = items_by_host.get(hid, [])
                total_items += len(host_items)

                tags = {}
                for t in h.get("tags") or []:
                    if "tag" in t:
                        tags[t["tag"]] = t.get("value", "")

                inventory = h.get("inventory") or {}

                interfaces_raw = h.get("interfaces") or []
                interfaces = []
                for iface in interfaces_raw:
                    desc = iface.get("description", "")
                    if not desc and isinstance(iface.get("details"), dict):
                        desc = iface["details"].get("description", "")
                    interfaces.append({
                        "interfaceid": iface["interfaceid"],
                        "type": int(iface.get("type", 1)),
                        "ip": iface.get("ip", ""),
                        "dns": iface.get("dns", ""),
                        "port": iface.get("port", ""),
                        "main": int(iface.get("main", 0)),
                        "useip": int(iface.get("useip", 1)),
                        "description": desc,
                    })

                host_interfaces_map: Dict[str, dict] = {}
                for item in host_items:
                    key = f"{item['interface_name']}|{item['interface_description']}"
                    if not item["interface_name"]:
                        continue
                    if key not in host_interfaces_map:
                        host_interfaces_map[key] = {
                            "interface_name": item["interface_name"],
                            "description": item["interface_description"],
                            "items": [],
                        }
                    host_interfaces_map[key]["items"].append({
                        "itemid": item["itemid"],
                        "name": item["name"],
                        "key_": item["key_"],
                        "lastvalue": item["lastvalue"],
                        "lastclock": item["lastclock"],
                    })

                new_router_entry = {
                    "hostid": hid,
                    "host": h.get("host", ""),
                    "name": h.get("name", h.get("host", "")),
                    "status": int(h.get("status", 0)),
                    "groups": [
                        {"groupid": g["groupid"], "name": g["name"]}
                        for g in (h.get("groups") or [])
                    ],
                    "templates": [
                        {"templateid": t["templateid"], "name": t["name"]}
                        for t in (h.get("parentTemplates") or [])
                    ],
                    "interfaces": interfaces,
                    "interface_items": sorted(
                        host_interfaces_map.values(),
                        key=lambda x: x["interface_name"],
                    ),
                    "tags": tags,
                    "inventory": inventory,
                    "macros": h.get("macros") or [],
                    "item_count": len(host_items),
                }

                if hid in router_map:
                    for i, router_in_db in enumerate(db["routers"]):
                        if router_in_db["hostid"] == hid:
                            db["routers"][i] = new_router_entry
                            break
                else:
                    db["routers"].append(new_router_entry)

            _write_progress()

        total_main_ifaces = sum(
            1 for r in db["routers"] for i in r["interfaces"] if i["main"]
        )
        total_snmp = sum(
            1 for r in db["routers"] for i in r["interfaces"] if i["type"] == 2
        )
        db["summary"] = {
            "total_routers": len(db["routers"]),
            "total_interfaces": sum(len(r["interfaces"]) for r in db["routers"]),
            "total_logical_interfaces": sum(len(r["interface_items"]) for r in db["routers"]),
            "total_items": total_items,
            "total_main_interfaces": total_main_ifaces,
            "total_snmp_interfaces": total_snmp,
        }

        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)

        logger.info(
            "Refreshed router DB: %d routers, %d logical interfaces, %d items -> %s",
            db["summary"]["total_routers"],
            db["summary"]["total_logical_interfaces"],
            db["summary"]["total_items"],
            db_path,
        )
        return db["summary"]

    @staticmethod
    def search_router_db(keyword: str, db_path: str,
                         search_host: bool = True,
                         search_interface: bool = True,
                         search_ip: bool = True,
                         case_sensitive: bool = False,
                         partial: bool = True) -> List[dict]:
        if not os.path.isfile(db_path):
            return []

        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)

        if not case_sensitive:
            term = keyword.lower()
        else:
            term = keyword

        results = []
        for router in db.get("routers", []):
            matched_interfaces = []
            matched_host = False
            matched_fields = {}

            if search_host:
                host_haystack = f"{router['host']} {router['name']}"
                if not case_sensitive:
                    host_haystack = host_haystack.lower()
                if (partial and term in host_haystack) or (not partial and host_haystack == term):
                    matched_host = True
                    matched_fields["host"] = router["host"]

            if search_interface:
                for iface in router.get("interface_items", []):
                    haystack = f"{iface['interface_name']} {iface['description']}"
                    if not case_sensitive:
                        haystack = haystack.lower()
                    if (partial and term in haystack) or (not partial and haystack == term):
                        matched_interfaces.append(iface)

            if search_ip:
                for iface in router.get("interfaces", []):
                    ip = iface.get("ip", "")
                    if not ip:
                        continue
                    haystack = ip
                    if not case_sensitive:
                        haystack = haystack.lower()
                    if (partial and term in haystack) or (not partial and haystack == term):
                        matched_interfaces.append({
                            "interface_name": "IP Match",
                            "description": ip,
                        })

            if matched_host or matched_interfaces:
                entry = {
                    "hostid": router["hostid"],
                    "host": router["host"],
                    "name": router["name"],
                    "status": router["status"],
                    "groups": router["groups"],
                    "templates": router["templates"],
                    "interfaces": router["interfaces"],
                    "tags": router["tags"],
                    "inventory": router["inventory"],
                    "macros": router["macros"],
                    "item_count": router["item_count"],
                }
                if matched_interfaces:
                    entry["matched_interfaces"] = matched_interfaces
                    entry["match_count"] = len(matched_interfaces)
                if matched_fields:
                    entry["matched_fields"] = matched_fields
                results.append(entry)

        return results

    def get_active_problems(self, hostids: List[str] = None,
                            min_severity: int = 0) -> List[ProblemInfo]:
        params = {
            "output": ["eventid", "objectid", "name", "severity", "clock", "acknowledged"],
            "selectHosts": ["hostid", "name", "host"],
            "recent": True,
            "sortfield": ["clock"],
            "sortorder": "DESC",
        }
        if hostids:
            params["hostids"] = hostids
        if min_severity > 0:
            params["severities"] = list(range(min_severity, 6))

        raw = self.request("problem.get", params)
        if not raw:
            return []

        problems = []
        for p in raw:
            pi = ProblemInfo.from_zabbix_dict(p)
            hosts = p.get("hosts") or []
            if hosts:
                pi.host = hosts[0].get("host", "")
            problems.append(pi)
        return problems

    def acknowledge_problem(self, eventid: str, message: str,
                            close: bool = False) -> bool:
        params = {
            "eventids": [eventid],
            "message": message,
            "action": 1,
        }
        if close:
            params["action"] = 2
        self.request("event.acknowledge", params)
        return True

    def get_trigger_history(self, triggerid: str,
                            limit: int = 10) -> List[TriggerEvent]:
        params = {
            "output": ["eventid", "objectid", "clock", "value", "name", "severity"],
            "select_acknowledges": "extend",
            "objectids": [triggerid],
            "source": 3,
            "object": 0,
            "sortfield": ["clock"],
            "sortorder": "DESC",
            "limit": limit,
        }
        raw = self.request("event.get", params)
        if not raw:
            return []
        return [TriggerEvent.from_zabbix_dict(e) for e in raw]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def create_maintenance(self, name: str, hostids: List[str],
                           duration_seconds: int,
                           description: str = "") -> str:
        now = int(time.time())
        params = {
            "name": name,
            "hostids": hostids,
            "active_since": str(now),
            "active_till": str(now + duration_seconds),
            "timeperiods": [
                {
                    "timeperiod_type": 0,
                    "start_date": now,
                    "period": duration_seconds,
                }
            ],
            "description": description,
        }
        result = self.request("maintenance.create", params)
        if result and "maintenanceids" in result:
            return result["maintenanceids"][0]
        raise ZabbixAPIError("maintenance.create did not return maintenanceids")

    def delete_maintenance(self, maintenanceid: str) -> bool:
        self.request("maintenance.delete", [maintenanceid])
        return True

    # ------------------------------------------------------------------
    # History & Data
    # ------------------------------------------------------------------

    def get_history(self, itemids: List[str], value_type: int,
                    time_from: int, time_till: int,
                    limit: int = 1000) -> List[HistoryRecord]:
        params = {
            "output": ["itemid", "clock", "value", "ns"],
            "history": value_type,
            "itemids": itemids,
            "time_from": time_from,
            "time_till": time_till,
            "sortfield": ["clock"],
            "sortorder": "ASC",
            "limit": limit,
        }
        raw = self.request("history.get", params)
        if not raw:
            return []
        return [HistoryRecord.from_zabbix_dict(h) for h in raw]

    def get_all_history_paginated(
        self, itemids: List[str], value_type: int,
        time_from: int, time_till: int,
        chunk_size: int = 1000,
    ) -> Generator[List[HistoryRecord], None, None]:
        current_from = time_from
        while current_from < time_till:
            params = {
                "output": ["itemid", "clock", "value", "ns"],
                "history": value_type,
                "itemids": itemids,
                "time_from": current_from,
                "time_till": time_till,
                "sortfield": ["clock"],
                "sortorder": "ASC",
                "limit": chunk_size,
            }
            raw = self.request("history.get", params)
            if not raw:
                break
            records = [HistoryRecord.from_zabbix_dict(h) for h in raw]
            yield records

            if len(records) < chunk_size:
                break

            last_clock = records[-1].clock
            last_ns = records[-1].ns
            current_from = last_clock
            if last_ns > 0:
                current_from += 1

    # ------------------------------------------------------------------
    # Scripts & Actions
    # ------------------------------------------------------------------

    def execute_script(self, scriptid: str, hostid: str) -> ScriptResult:
        params = {
            "scriptid": scriptid,
            "hostid": hostid,
        }
        raw = self.request("script.execute", params)
        return ScriptResult.from_zabbix_dict(raw)

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def get_api_version(self) -> str:
        return self.request("apiinfo.version")

    def health_check(self) -> bool:
        try:
            ver = self.get_api_version()
            return bool(ver)
        except ZabbixBaseError as e:
            logger.error("Health check failed: %s", e)
            return False


def create_zabbix_service(ini_path: str = None, **overrides) -> ZabbixService:
    config = ZabbixConfig.resolve(ini_path=ini_path, overrides=overrides if overrides else None)
    return ZabbixService(config)
