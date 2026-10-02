# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib

# 1. 제공해주신 MS SQL Server LocalDB 접속 정보를 완벽하게 반영
SERVER = '(localdb)\\MSSQLLocalDB'
DATABASE = 'NAIS_NEXT_ERP'

# pyodbc 드라이버를 사용하여 명시적으로 SQL Server Native 커넥션을 수립합니다.
# 제공해주신 보안 및 세션 제어 옵션을 완벽히 이식합니다.
conn_str = (
    f"Driver={{ODBC Driver 17 for SQL Server}};"
    f"Server={SERVER};"
    f"Database={DATABASE};"
    f"Trusted_Connection=yes;"
    f"PersistSecurityInfo=False;"
    f"Pooling=False;"
    f"MultipleActiveResultSets=False;"
    f"Encrypt=yes;"
    f"TrustServerCertificate=yes;"
)

# SQLAlchemy 체계에 맞게 ODBC 연결 규격을 URL 인코딩 처리
DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(conn_str)}"

# 2. 데이터베이스 엔진 생성
engine = create_engine(
    DATABASE_URL,
    echo=False  # SQL 실행 로그를 보고 싶으시다면 True로 변경하세요
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()