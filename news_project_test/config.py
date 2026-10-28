#############################
# [POSTGRESQL 설정]
#############################

# /bin 경로
POSTGRES_BIN = "C:/Program Files/PostgreSQL/18/bin"

# /data 경로
SAVE_PATH = "C:/Program Files/PostgreSQL/18/data"

# 백업 경로
BACKUP_PATH = ""

# 접속 설정
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "postgres"

# 사용할 데이터베이스 이름
DB_NAME = "News DataBase"

#############################
# [RSS 피드 설정]
#############################

# 뉴스 RSS
MEDIA_RSS = {
    "보안뉴스": {
        "보안 뉴스": "https://www.boannews.com/rss/allArticle.xml"
    },
    "전국일간지": {
        "경향신문": [
            "https://www.khan.co.kr/rss/rssdata/total_news.xml"
        ],
        "국민일보": [
            "https://www.kmib.co.kr/rss/data/kmibPolRss.xml", #정치
            "https://www.kmib.co.kr/rss/data/kmibEcoRss.xml", #경제
            "https://www.kmib.co.kr/rss/data/kmibSocRss.xml", #사회
            "https://www.kmib.co.kr/rss/data/kmibIntRss.xml", #국제
            "https://www.kmib.co.kr/rss/data/kmibEntRss.xml", #연예
            "https://www.kmib.co.kr/rss/data/kmibSpoRss.xml", #스포츠
            "https://www.kmib.co.kr/rss/data/kmibGolfRss.xml", #골프
            "https://www.kmib.co.kr/rss/data/kmibLifeRss.xml", #라이프
            "https://www.kmib.co.kr/rss/data/kmibTraRss.xml" #여행
        ]
    }
}

# 선택된 뉴스 RSS
SELECTED_RSS = ['보안 뉴스']

#############################
# [설치된 라이브러리 확인]
#############################

INSTALLED_LIBRARIES = ['PySide6', 'aiohttp', 'asyncpg', 'pgvector', 'feedparser', 'trafilatura', 'numpy', 'kiwipiepy']

#############################
# [설정한 UI 테마 확인]
#############################

UI_THEME = 'light'
