import urllib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. 제공해주신 MS SQL 접속 정보를 Python URL 인코딩 형식에 맞게 구성
# (localdb)\MSSQLLocalDB 스래시 처리를 위해 인코딩 적용 또는 pymssql 형태 변환
# 데이터베이스명은 'NAIS_NEXT_ERP'로 가정하여 세팅합니다.
SERVER = '(localdb)\\MSSQLLocalDB'
DATABASE = 'NAIS_NEXT_ERP'

# pymssql 연동 문자열 구성 (통합 인증 Integrated Security=True 반영)
# Windows 통합 인증 환경에서는 아래와 같이 호스트 명을 지정합니다.
DATABASE_URL = f"mssql+pymssql://{SERVER}/{DATABASE}?trusted=True"

# 2. SQLAlchemy Engine 생성 (제조 데이터 처리 최적화 옵션 반영)
engine = create_engine(
    DATABASE_URL,
    pool_size=10,         # 커넥션 풀 크기 (제공해주신 Pooling=False 대응 및 웹 성능 확보)
    max_overflow=20,     # 대량 요청 시 추가 허용 커넥션
    pool_recycle=1800,   # 30분 주기로 커넥션 재사용 (커넥션 끊김 방지)
    echo=False           # 실제 운영 환경에서는 SQL 로그 출력을 꺼둡니다 (성능 최적화)
)

# 3. 세션 및 ORM Base 정의
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# FastAPI 의존성 주입을 위한 DB 세션 라이프사이클 관리 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()