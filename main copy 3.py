import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import create_engine, text

app = FastAPI(title="NERP Core API System", version="1.0.1")

# 사용하시는 MS-SQL 인프라 환경에 맞게 접속 문자열을 지정하세요.
DATABASE_URL = "mssql+pyodbc://sa:YourPassword@localhost:1433/NERP?driver=ODBC+Driver+17+for+SQL+Server"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)


@app.post("/api/v1/setup/upload-users-new", tags=["기준정보 설정"])
async def upload_user_master_new(file: UploadFile = File(...)):
    """
    [개선판] 기준정보 엑셀/CSV 업로드 처리 API
    - 최신 Pandas 버젼 호환 (.map 적용)
    - 사용자 인지 편의를 위한 요약 리포트 통계 반환 기능 추가
    """
    filename = file.filename
    extension = filename.split(".")[-1].lower()
    
    if extension not in ["xlsx", "xls", "csv"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="⚠️ 엑셀(.xlsx, .xls) 또는 CSV 파일 포맷만 업로드 가능합니다."
        )
    
    try:
        contents = await file.read()
        if extension == "csv":
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        # [에러 해결]: applymap 대신 최신 표준인 map 함수를 적용하여 결측치 및 양끝 공백 제거
        df = df.fillna("")
        df = df.map(lambda x: str(x).strip() if isinstance(x, str) else x)

        # 필수 검증 항목 체크
        required_cols = ["COMPANYCODE", "LOGINID", "PASSWORD", "DISPLAYNAME"]
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"❌ 업로드 템플릿 양식이 잘못되었습니다. 필수 항목인 [{col}] 컬럼이 존재하지 않습니다."
                )

        # 데이터 변환 레이어 가공
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
        upload_df["ROLE_CD"] = "USER" 

        # UI 가독성을 극대화하기 위한 요약 리포트 통계 가공
        summary_report = []
        if not upload_df.empty:
            # 회사코드, 회사명 그룹핑 카운트 산출
            grp = df.groupby(["COMPANYCODE", df.get("COMPANY", "미지정")]).size().reset_index(name="CNT")
            for _, r in grp.iterrows():
                summary_report.append(f"• {r[1]} ({r[0]}): {r['CNT']}명")

        # NERP DB 원자성 반영 트랜잭션
        with engine.begin() as connection:
            # 기존 마스터 클렌징
            connection.execute(text("TRUNCATE TABLE MA_USER;"))
            
            # 고속 벌크 인서트 인젝션
            upload_df.to_sql(
                name="MA_USER", 
                con=connection, 
                if_exists="append", 
                index=False,
                chunksize=1000
            )

        # UI 친화적인 성공 피드백 객체 반환
        return {
            "status": "success",
            "title": "🎉 기준정보 반영 성공",
            "message": f"업로드하신 '{filename}' 파일이 NERP 시스템에 정상 적재되었습니다.",
            "total_count": f"총 {len(upload_df)} 건 처리 완료",
            "details": summary_report  # UI 단에서 리스트 형태로 뿌려줄 수 있도록 지원
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"🔥 NERP DB 연동 처리 중 트랜잭션 장애가 발생했습니다. (오류 요인: {str(e)})"
        )