#############################
# [POSTGRESQL 설정]
#############################

# /bin 경로
POSTGRES_BIN = r"C:/Program Files/PostgreSQL/18/bin"

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
DB_NAME = "News_Data_Server"

#############################
# [RSS 피드 설정]
#############################

# 뉴스 RSS
MEDIA_RSS = {
    "보안뉴스": {
        "보안 뉴스": "https://www.boannews.com/rss/allArticle.xml"
    }
}

# 선택된 뉴스 RSS
SELECTED_RSS = ['보안 뉴스']