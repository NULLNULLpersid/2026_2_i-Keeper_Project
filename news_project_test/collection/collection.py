"""수집 시작·DB 연결 수명주기·중단 신호를 관리한다."""
import asyncio
from init import config
from db import connection as db_connection
from .crawler.collect_news import collect_with_connection


def collect_news_cycle(urls, path, cancel_event, ui_callback, file_logger):
    """GUI 작업 스레드용 진입점. 기존 GUI 호출 인수를 유지한다."""
    return asyncio.run(_async_collect_news_cycle(urls, cancel_event, ui_callback, file_logger, path))


async def _async_collect_news_cycle(urls, cancel_event, ui_callback, file_logger, path=None):
    if cancel_event.is_set():
        return None
    # 최초 서버 준비는 완료한 후 취소 신호를 확인한다.
    async with db_connection.configured_database(config, storage_path=path or config.SAVE_PATH) as connection:
        if cancel_event.is_set():
            return None
        task = asyncio.create_task(collect_with_connection(connection, urls, ui_callback, file_logger))
        try:
            while not task.done():
                if cancel_event.is_set():
                    task.cancel()
                    break
                await asyncio.wait({task}, timeout=0.1)
            return await task
        except asyncio.CancelledError:
            if not cancel_event.is_set():
                raise
            file_logger.info("수집 종료 요청: HTTP/DB 작업 취소 및 연결 정리")
            return None
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)