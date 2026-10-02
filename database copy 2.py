# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib

# 1. 제공해주신 MS SQL Server LocalDB 접속 정보 분석 및 적용
SERVER = '(localdb)\\MSSQLLocalDB'
DATABASE = 'NAIS_NEXT_ERP'

# 2. pymssql의 파라미터 전달 오류(trusted)를 우회하고 Windows 통합 인증을 확실하게 처리하는 형태
# 서버 명에 특수문자()가 있으므로 명시적으로 포트를 매핑하거나 주소를 인코딩하여 연결 안정성을 확보합니다.
params = f"server={SERVER};database={DATABASE};integrated Security=true;encrypt=true;trustServerCertificate=true"
DATABASE_URL = f"mssql+pymssql:///?odbc_connect={urllib.parse.quote_plus(params)}"

# 3. 대규모 트랜잭션 및 웹 환경을 고려한 DB 엔진 생성
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()