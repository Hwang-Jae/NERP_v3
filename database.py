# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib

# 1. MS SQL Server LocalDB 접속 정보 정의
SERVER = '(localdb)\\MSSQLLocalDB'
DATABASE = 'NAIS_NEXT_ERP'

# 로컬 LocalDB 환경에 맞춤형 ODBC 연결 문자열 구성
# Encrypt=no로 변경하여 암호화 미지원 오류를 방지합니다.
conn_str = (
    f"Driver={{ODBC Driver 17 for SQL Server}};"
    f"Server={SERVER};"
    f"Database={DATABASE};"
    f"Trusted_Connection=yes;"
    f"Encrypt=no;"  # <- 핵심: 로컬 환경에서는 암호화를 끕니다.
)

# SQLAlchemy 규격에 맞게 URL 인코딩 처리
DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(conn_str)}"

# 2. 데이터베이스 엔진 생성
engine = create_engine(
    DATABASE_URL,
    echo=False  # SQL 쿼리 로그를 보고 싶으시다면 True로 변경하세요.
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()