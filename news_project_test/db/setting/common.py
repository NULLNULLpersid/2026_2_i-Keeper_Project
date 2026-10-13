"""DB 설정 도구에서 공유하는 안전한 실행 로그."""
from __future__ import annotations

import inspect
import logging
import threading
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "db.log"
_LOGGER = logging.getLogger("db.database")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_LOG_LOCK = threading.Lock()
_LOG_PASSWORD = ContextVar("db_log_password", default="")

class _PrivateFormatter(logging.Formatter):
    def format(self, record):
        rendered = super().format(record)
        password = _LOG_PASSWORD.get()
        return rendered.replace(password, "[REDACTED]") if password else rendered

def _configure_logging():
    with _LOG_LOCK:
        if not _LOGGER.handlers:
            handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
            handler.setFormatter(_PrivateFormatter(
                "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
            ))
            _LOGGER.addHandler(handler)
    return _LOGGER

def _logged(function):
    """실행 시작/완료/오류 기록. 인수는 기록하지 않고 원래 예외를 전달한다."""
    signature = inspect.signature(function)

    def begin(args, kwargs):
        logger = _configure_logging()
        values = signature.bind_partial(*args, **kwargs).arguments
        token = _LOG_PASSWORD.set(values.get("password", _LOG_PASSWORD.get()))
        logger.info("실행 시작: %s", function.__name__)
        return logger, token

    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            logger, token = begin(args, kwargs)
            try:
                result = await function(*args, **kwargs)
                logger.info("실행 완료: %s", function.__name__)
                return result
            except BaseException:
                logger.exception("실행 오류: %s", function.__name__)
                raise
            finally:
                _LOG_PASSWORD.reset(token)
        return asynchronous

    @wraps(function)
    def synchronous(*args, **kwargs):
        logger, token = begin(args, kwargs)
        try:
            result = function(*args, **kwargs)
            logger.info("실행 완료: %s", function.__name__)
            return result
        except BaseException:
            logger.exception("실행 오류: %s", function.__name__)
            raise
        finally:
            _LOG_PASSWORD.reset(token)
    return synchronous