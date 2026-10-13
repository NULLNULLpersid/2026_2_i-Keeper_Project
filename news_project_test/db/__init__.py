"""DB 기능을 수집기와 연결하는 facade."""
from __future__ import annotations

# db 패키지는 다른 모듈이 DB 기능을 호출하는 공통 진입점이다.
# 실제 SQL과 트랜잭션은 아래에서 가져온 DB 모듈 함수가 처리한다.
# 이 파일을 import하는 것만으로 서버를 가동하거나 DB에 접속하지 않는다.

# 설정 모듈: 저장·중복 비교에 사용하는 HTTP(S) URL 형식 검사 기능(원본 유지).
from .setting import validate_url
# 테이블 관리 모듈: 기사 발행시각에 따라 본문 테이블을 이동한다.
from .table_manager import archive_news
# 저장 모듈: 기사·키워드·임베딩·학습 데이터·분석 결과 저장.
# SaveResult는 기사 ID(news_id)와 신규 저장 여부(created)를 담는 반환 형식이다.
from .pipeline.save import (
    SaveResult, save_category, save_keywords, save_embedding, save_news,
    save_learning_data, create_analysis_run, save_analysis_results,
    mark_analysis_failed,
)
# 조회 모듈: 중복 URL, 발행시각, 기사 본문 및 분석 관련 데이터 조회.
from .pipeline.extract import (
    get_existing_urls, get_last_news_time, get_news, list_news, get_keywords,
    get_embedding, find_similar_news, get_analysis_results,
)


# 위 함수들은 import를 통해 모듈 API로도 공개된다.
#   await db.save_news(connection, publisher_name=..., ...)
# 아래 클래스는 connection을 보관하여 매번 연결 인수를 전달하지 않게 한다.
#   manager = db.DatabaseManager(connection)
#   await manager.save_news(publisher_name=..., ...)
# 두 호출 방법은 같은 DB 구현 함수를 실행한다.
class DatabaseManager:
    """하나의 asyncpg 연결을 통해 저장·조회·기사 이동 기능을 제공한다."""

    def __init__(self, connection):
        # 호출자가 생성한 asyncpg.Connection을 보관한다. 연결 생성·종료는 호출자 책임이다.
        # 같은 연결의 DB 작업은 순차 실행한다. 동시 DB 작업에는 별도 연결이 필요하다.
        self.connection = connection

    async def save_category(self, name, parent_id=None):
        # 카테고리를 등록하거나 기존 ID를 조회한다. parent_id는 상위 카테고리 ID이다.
        return await save_category(self.connection, name, parent_id)

    async def save_news(self, **kwargs):
        # kwargs를 DB 저장 함수에 그대로 전달한다. 필수 입력은 언론사명·제목·URL·발행시각·본문이다.
        # SaveResult.created가 True면 신규 기사, False면 기존 중복 기사이다.
        return await save_news(self.connection, **kwargs)

    async def save_keywords(self, news_id, keywords):
        # 기사별 키워드와 점수·순위를 저장한다. 공용 키워드 ID는 DB 저장 모듈에서 재사용한다.
        return await save_keywords(self.connection, news_id, keywords)

    async def save_embedding(self, news_id, *, model_name, embedding):
        # news_id의 임베딩을 모델명과 함께 저장한다. 모델 차원 검사와 연도별 저장은 DB 모듈이 담당한다.
        return await save_embedding(self.connection, news_id, model_name=model_name, embedding=embedding)

    async def save_learning_data(self, news_id, **kwargs):
        # 해당 기사를 학습 데이터셋에 연결한다. kwargs에는 데이터셋명·버전·분할 정보 등을 전달한다.
        return await save_learning_data(self.connection, news_id, **kwargs)

    async def create_analysis_run(self, **kwargs):
        # 분석 실행 정보를 등록하고 실행 ID를 반환한다. 기간·모델·필터·알고리즘 정보는 kwargs로 전달한다.
        return await create_analysis_run(self.connection, **kwargs)

    async def save_analysis_results(self, analysis_id, results):
        # 분석 ID에 대응하는 통계와 이슈 결과를 저장한다. results 구조는 DB 저장 함수에서 처리한다.
        return await save_analysis_results(self.connection, analysis_id, results)

    async def mark_analysis_failed(self, analysis_id):
        # 지정한 분석 실행을 실패 상태로 변경한다.
        return await mark_analysis_failed(self.connection, analysis_id)

    async def archive_news(self, *, batch_size=1000):
        # 24시간이 지난 기사를 today_news에서, 3년이 지난 기사를 news에서 이동한다.
        # 영구 news_id와 부가 데이터 연결은 유지한다. batch_size는 한 번에 이동할 최대 행 수이다.
        return await archive_news(self.connection, batch_size=batch_size)

    async def get_news(self, news_id):
        # today_news·news·old_news를 통합 조회하여 해당 news_id의 기사 1건을 반환한다.
        return await get_news(self.connection, news_id)

    async def list_news(self, **filters):
        # 기간·언론사·카테고리·작성자·페이지 조건을 전달하여 기사 목록을 조회한다.
        return await list_news(self.connection, **filters)

    async def get_existing_urls(self, urls):
        # today_news의 원본 URL을 직접 비교하여 이미 저장된 URL 집합을 반환한다.
        # 수집 전 중복 후보 조회용이며, 최종 중복 검사는 저장 함수에서도 수행한다.
        return await get_existing_urls(self.connection, urls)

    async def get_last_news_time(self, publisher_name):
        # 해당 언론사의 today_news·news·old_news에서 가장 최근 기사 발행시각을 조회한다.
        # 수집 시각이 아닌 published_at 기준이다. 저장된 기사가 없으면 None을 반환한다.
        return await get_last_news_time(self.connection, publisher_name)

    async def get_keywords(self, news_id):
        # 기사에 연결된 키워드와 점수·순위를 순위 순서로 반환한다.
        return await get_keywords(self.connection, news_id)

    async def get_embedding(self, news_id, model_id):
        # 기사와 모델 ID에 해당하는 임베딩을 locator를 통해 조회한다.
        return await get_embedding(self.connection, news_id, model_id)

    async def find_similar_news(self, news_id, model_id, *, limit=20):
        # 같은 모델의 임베딩을 코사인 유사도로 비교한다. limit은 추천 기사 최대 개수이다.
        return await find_similar_news(self.connection, news_id, model_id, limit=limit)

    async def get_analysis_results(self, analysis_id):
        # 분석 실행 정보, 전체 통계, 이슈 및 하위 결과를 일관된 읽기 스냅샷으로 반환한다.
        return await get_analysis_results(self.connection, analysis_id)