import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import create_engine, text

app = FastAPI(title="NERP Core API System", version="1.0.0")

# =========================================================================
# [중요] 사용하시는 MS-SQL 인프라 환경에 맞게 접속 연결 문자열(Connection String)을 수정하세요.
# =========================================================================
# SQL Server 인증 방식 예시
DATABASE_URL = "mssql+pyodbc://sa:mobis3#!@localhost:1433/NERP?driver=ODBC+Driver+17+for+SQL+Server"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)


# 1. 엑셀 업로드 및 NERP DB 적재 API
@app.post("/api/v1/setup/upload-users-new", tags=["기준정보 설정"])
async def upload_user_master_new(file: UploadFile = File(...)):
    """
    새로운 기준정보_new 양식(xlsx/csv)을 업로드 받아 NERP.MA_USER 테이블에 벌크 갱신 처리합니다.
    """
    filename = file.filename
    extension = filename.split(".")[-1].lower()
    
    if extension not in ["xlsx", "xls", "csv"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Excel(.xlsx) 또는 CSV 파일 포맷만 처리 가능합니다."
        )
    
    try:
        # 파일 바이너리 읽기 및 데이터프레임 변환
        contents = await file.read()
        if extension == "csv":
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        # 결측치 정제 및 공백 제거
        df = df.fillna("")
        df = df.applymap(lambda x: str(x).strip() if isinstance(x, str) else x)

        # 필수 제약 컬럼 유효성 검증
        required_cols = ["COMPANYCODE", "LOGINID", "PASSWORD", "DISPLAYNAME"]
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"양식 스키마가 불일치합니다. 필수 컬럼 누락: {col}"
                )

        # DB 적재 규격에 일치하도록 데이터프레임 매핑 및 가공
        upload_df = pd.DataFrame()
        upload_df["LOGIN_ID"] = df["LOGINID"]
        upload_df["COMPANY_CD"] = df["COMPANYCODE"]
        upload_df["COMPANY_NM"] = df.get("COMPANY", "")
        upload_df["PASSWORD"] = df["PASSWORD"]
        upload_df["EMAIL"] = df.get("EMAIL", "")
        upload_df["DEPT_CD"] = df.get("MAINDEPTCODE", "")
        upload_df["DEPT_NM"] = df.get("DEPTNAME", "")
        upload_df["TEAM_CHIEF_YN"] = df.get("TEAMCHIEFYN", "N").str.upper().apply(lambda x: 'Y' if x == 'Y' else 'N')
        upload_df["USE_YN"] = df.get("DISPLAYYN", "Y").str.upper().apply(lambda x: 'Y' if x == 'Y' else 'N')
        upload_df["USER_NM"] = df["DISPLAYNAME"]
        upload_df["DUTY_CD"] = df.get("DUTYCODE", "")
        upload_df["DUTY_NM"] = df.get("DUTYNAME", "")
        upload_df["RANK_CD"] = df.get("RANKCODE", "")
        upload_df["RANK_NM"] = df.get("RANKNAME", "")
        upload_df["CELL_PHONE"] = df.get("CELLPHONE", "")
        upload_df["JOB_DESC"] = df.get("JOBDESC", "")
        upload_df["MAIN_YN"] = df.get("MAINYN", "Y").str.upper().apply(lambda x: 'Y' if x == 'Y' else 'N')
        upload_df["ROLE_CD"] = "USER" # 초기 기본 권한 세팅

        # 데이터베이스 동기화 트랜잭션 실행
        with engine.begin() as connection:
            # 1단계: 마스터 테이블 클렌징 (기존 데이터 비우기 또는 이관)
            connection.execute(text("TRUNCATE TABLE MA_USER;"))
            
            # 2단계: pandas high-speed 벌크 인서트 수행
            upload_df.to_sql(
                name="MA_USER", 
                con=connection, 
                if_exists="append", 
                index=False,
                chunksize=1000 # 1,000건 단위 분할 전송으로 성능 보장
            )

        return {
            "status": "success",
            "database": "NERP",
            "target_table": "MA_USER",
            "imported_rows": len(upload_df),
            "message": f"성공적으로 '{filename}' 파일 분석 및 데이터 적재를 완료했습니다."
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"NERP 서버 트랜잭션 장애 발생: {str(e)}"
        )


# 2. 통합 로그인 및 DB 인증 연동 엔드포인트
class LoginRequest(BaseModel):
    username: str  # 입력 폼 상의 LOGINID
    password: str  # 입력 폼 상의 PASSWORD

@app.post("/api/v1/auth/login", tags=["인증 관리"])
async def login_authentication(data: LoginRequest):
    """
    MA_USER 테이블을 직접 쿼리하여 LOGINID와 PASSWORD 기반의 일치 여부를 검증합니다.
    """
    query = text("""
        SELECT LOGIN_ID, USER_NM, DEPT_NM, RANK_NM, ROLE_CD, USE_YN 
        FROM MA_USER 
        WHERE LOGIN_ID = :login_id AND PASSWORD = :password
    """)
    
    with engine.connect() as connection:
        result = connection.execute(query, {"login_id": data.username, "password": data.password}).fetchone()
        
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )
        
    if result.USE_YN == 'N':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="비활성화된 계정입니다. 시스템 관리자에게 문의하세요."
        )

    return {
        "status": "success",
        "message": f"{result.USER_NM}님, 환영합니다.",
        "session_user": {
            "login_id": result.LOGIN_ID,
            "display_name": f"{result.USER_NM} {result.RANK_NM}",
            "department": result.DEPT_NM,
            "role": result.ROLE_CD
        },
        "redirect_url": "/dashboard"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)