import io
import os
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, text

app = FastAPI(
    title="NERP Next-Gen Core Engine",
    description="NVH KOREA 차세대 ERP 웹 백엔드 시스템",
    version="3.5.3"
)

# =========================================================================
# [주의] 사용자 제공 MS-SQL 공식 연결 주소 반영 (sa 계정 인증 및 NERP 데이터베이스)
# =========================================================================
DATABASE_URL = "mssql+pyodbc://sa:mobis3#!@localhost:1433/NERP?driver=ODBC+Driver+17+for+SQL+Server"

# 대량 트랜잭션 성능 및 커넥션 누수를 제어하기 위한 엔진 튜닝
engine = create_engine(
    DATABASE_URL,
    pool_size=15,
    max_overflow=25,
    pool_recycle=1800,
    echo=False
)

# =========================================================================
# [크롬 개발자도구 404 에러 차단 방어선]
# Chrome DevTools가 자동으로 탐색하는 디버그 파일을 200 OK 무음 응답으로 대응합니다.
# =========================================================================
@app.get("/.well-known/appspecific/com.chrome.devtools.json", tags=["시스템 관리"])
def handle_chrome_devtools_request():
    """
    크롬 개발자 도구의 자동 디버깅용 프로파일 탐색 시, 404 에러 출력을 차단하기 위한 빈 200 응답 핸들러입니다.
    """
    return JSONResponse(status_code=200, content={})

# 1. 동적 권한 관리를 위한 조직도 트리 조회 API
@app.get("/api/v1/auth/dept-tree", tags=["인증/권한"])
def get_dept_tree():
    """
    사용자가 로그인 시 소속을 쉽게 선택할 수 있도록 조직도를 계층형 트릴로 제공합니다.
    """
    return [
        {
            "id": "CORP_ROOT", "name": "엔브이에이치코리아 법인 연합", "icon": "fa-building-columns", "open": True,
            "children": [
                {
                    "id": "1000", "name": "엔브이에이치코리아 (본사)", "icon": "fa-building",
                    "depts": ["구매팀", "연구소", "IT지원팀", "생산관리팀"]
                },
                {
                    "id": "6000", "name": "엔브이에이치플로어시스템", "icon": "fa-industry",
                    "depts": ["개발파트", "재무팀", "생산기술팀"]
                },
                {
                    "id": "6100", "name": "엔브이에이치오버헤드시스템", "icon": "fa-industry",
                    "depts": ["개발/신차품질팀", "생산파트"]
                },
                {
                    "id": "7300", "name": "NVHUSA (해외법인)", "icon": "fa-earth-americas",
                    "depts": ["인사총무팀", "생산생관팀"]
                },
                {
                    "id": "5000", "name": "NTM (협력사)", "icon": "fa-handshake",
                    "depts": ["영업개발사업부", "협력업체"]
                }
            ]
        }
    ]

# 2. 기준정보 신규 엑셀 업로드 및 MSSQL 이중 트랜잭션 적재 API
@app.post("/api/v1/setup/upload-users-new", tags=["기준정보 설정"])
async def upload_user_master_new(file: UploadFile = File(...)):
    """
    기준정보_new 엑셀/CSV 양식을 분석하여 안전하게 NERP 데이터베이스에 벌크로 적재합니다.
    """
    filename = file.filename
    extension = filename.split(".")[-1].lower()
    
    if extension not in ["xlsx", "xls", "csv"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="⚠️ 파일 형식이 어긋납니다. (.xlsx, .xls, .csv) 확장자만 제공해 주세요."
        )
    
    try:
        contents = await file.read()
        if extension == "csv":
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        # 결측치를 빈 문자열로 안전하게 채움
        df = df.fillna("")

        # 엑셀 파일 필수 스키마 제약조건 검증
        required_cols = ["COMPANYCODE", "LOGINID", "PASSWORD", "DISPLAYNAME"]
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"❌ 엑셀 형식이 다릅니다. 필수 항목인 [{col}] 열이 식별되지 않습니다."
                )

        # 안전한 데이터 전처리를 위해 개별 직렬화 및 양끝 공백 문자열 제거 적용
        def clean_col(column_name, default=""):
            if column_name in df.columns:
                return df[column_name].astype(str).str.strip()
            return pd.Series([default] * len(df))

        # DB 구조에 부합하도록 컬럼 리매핑 설계 (타입 안전성 보강)
        upload_df = pd.DataFrame()
        upload_df["LOGIN_ID"] = clean_col("LOGINID")
        upload_df["COMPANY_CD"] = clean_col("COMPANYCODE")
        upload_df["COMPANY_NM"] = clean_col("COMPANY")
        upload_df["PASSWORD"] = clean_col("PASSWORD")
        upload_df["EMAIL"] = clean_col("EMAIL")
        upload_df["DEPT_CD"] = clean_col("MAINDEPTCODE")
        upload_df["DEPT_NM"] = clean_col("DEPTNAME")
        
        # 가공 및 검증 처리
        upload_df["TEAM_CHIEF_YN"] = clean_col("TEAMCHIEFYN", "N").str.upper().apply(lambda x: 'Y' if x == 'Y' else 'N')
        upload_df["USE_YN"] = clean_col("DISPLAYYN", "Y").str.upper().apply(lambda x: 'Y' if x == 'Y' else 'N')
        upload_df["USER_NM"] = clean_col("DISPLAYNAME")
        upload_df["DUTY_CD"] = clean_col("DUTYCODE")
        upload_df["DUTY_NM"] = clean_col("DUTYNAME")
        upload_df["RANK_CD"] = clean_col("RANKCODE")
        upload_df["RANK_NM"] = clean_col("RANKNAME")
        upload_df["CELL_PHONE"] = clean_col("CELLPHONE")
        upload_df["JOB_DESC"] = clean_col("JOBDESC")
        upload_df["MAIN_YN"] = clean_col("MAINYN", "Y").str.upper().apply(lambda x: 'Y' if x == 'Y' else 'N')
        
        # 권한 부여 규칙 수립
        upload_df["ROLE_CD"] = clean_col("DEPTNAME").apply(lambda x: 'SYS_ADMIN' if 'ICT' in str(x) or 'IT' in str(x) else 'USER')

        # 요약 통계 결과 도출 (UI 바인딩용)
        summary_details = []
        if not upload_df.empty:
            # groupby 연산 중 문자열 매핑 충돌 방지를 위해 원본 데이터 정합 처리 후 카운트 계산
            df_temp = pd.DataFrame()
            df_temp["COMPANYCODE"] = clean_col("COMPANYCODE")
            df_temp["COMPANY"] = clean_col("COMPANY", "미지정")
            grp = df_temp.groupby(["COMPANYCODE", "COMPANY"]).size().reset_index(name="CNT")
            for _, r in grp.iterrows():
                summary_details.append(f"🏢 {r['COMPANY']} ({r['COMPANYCODE']}): {r['CNT']}명 수집 완료")

        # NERP DB 안전 트랜잭션 커밋
        with engine.begin() as connection:
            # 1. 안전하게 클렌징 처리 수행
            connection.execute(text("TRUNCATE TABLE MA_USER;"))
            
            # 2. 벌크 고속 로드
            upload_df.to_sql(
                name="MA_USER", 
                con=connection, 
                if_exists="append", 
                index=False,
                chunksize=1000
            )

        return {
            "status": "success",
            "title": "🎉 기준정보 업로드 성공",
            "message": f"업로드한 '{filename}' 파일 분석이 완료되었습니다.",
            "total_count": f"총 {len(upload_df)}명의 사용자 정보가 최신화되었습니다.",
            "details": summary_details
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"🔥 DB 적재 트랜잭션 처리 중 오류가 발생했습니다: {str(e)}"
        )

# 3. 사용자 인증 및 DB 매핑 검증 API
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/v1/auth/login", tags=["인증 관리"])
async def login_authentication(data: LoginRequest):
    """
    MA_USER 테이블을 직접 스캔하여 통합 로그인을 처리합니다.
    """
    query = text("""
        SELECT TOP 1 LOGIN_ID, USER_NM, DEPT_NM, RANK_NM, ROLE_CD, USE_YN, COMPANY_NM
        FROM MA_USER 
        WHERE LOGIN_ID = :login_id AND PASSWORD = :password
    """)
    
    with engine.connect() as connection:
        result = connection.execute(query, {"login_id": data.username, "password": data.password}).fetchone()
        
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="❌ 입력하신 사원 ID 또는 패스워드가 마스터 테이블과 일치하지 않습니다."
        )
        
    if result.USE_YN == 'N':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="⚠️ 비활성화 계정입니다. 시스템 주관 팀에 권한 할당을 요청하십시오."
        )

    return {
        "status": "success",
        "message": "인증 성공",
        "session_user": {
            "login_id": result.LOGIN_ID,
            "display_name": f"{result.USER_NM} {result.RANK_NM}",
            "department": result.DEPT_NM,
            "company": result.COMPANY_NM,
            "role": result.ROLE_CD
        }
    }

# 4. 웹 UI 어플리케이션 서빙 라우터
@app.get("/", response_class=HTMLResponse, tags=["UI 화면"])
def get_web_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>[index.html] 웹 UI 리소스 파일을 가져오는 데 실패했습니다. 파일을 다시 생성해 주세요.</h3>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)