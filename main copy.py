from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import engine, get_db
import models
from fastapi.responses import HTMLResponse
import os

# 데이터베이스 테이블 초기 생성 (최초 1회 실행)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Next Generation Web ERP - MS SQL Server Core", version="2.5")

# --- Pydantic 데이터 검증 DTO ---
class ProductionCreate(BaseModel):
    work_date: str
    line_cd: str
    item_cd: str
    prod_qty: float
    wh_cd: str = "WH01"

# --- 생산 실적 및 실시간 MS SQL 자재 수불 API ---
@app.post("/api/v1/production", status_code=status.HTTP_201_CREATED)
def register_production_and_backflush(prod: ProductionCreate, db: Session = Depends(get_db)):
    """
    생산 실적 등록 시 MS SQL 트랜잭션을 사용하여 자재 현재고를 원자적으로 차감합니다.
    """
    # 1. MS SQL 명시적 트랜잭션 블록 시작
    try:
        # [Step 1] 생산 완료된 제품의 현재고 조회 (행 잠금 설정으로 동시성 정합성 보장)
        prod_stock = db.query(models.StockMaster).filter(
            models.StockMaster.item_cd == prod.item_cd,
            models.StockMaster.wh_cd == prod.wh_cd
        ).with_for_update().first()  # MS SQL 'WITH (UPDLOCK)' 효과

        if not prod_stock:
            prod_stock = models.StockMaster(item_cd=prod.item_cd, wh_cd=prod.wh_cd, curr_qty=0.0)
            db.add(prod_stock)
        
        prod_stock.curr_qty += prod.prod_qty

        # [Step 2] 제품에 연결된 BOM 구조 조회 (정개 계산)
        bom_components = db.query(models.BomStructure).filter(
            models.BomStructure.parent_cd == prod.item_cd,
            models.BomStructure.use_flg == 'Y'
        ).all()

        consumed_materials = []
        
        # [Step 3] 하위 자재 소요량 계산 및 실시간 차감
        for component in bom_components:
            total_req_qty = component.req_qty * prod.prod_qty
            
            # 자재 재고 row 조회 및 잠금
            mat_stock = db.query(models.StockMaster).filter(
                models.StockMaster.item_cd == component.child_cd,
                models.StockMaster.wh_cd == prod.wh_cd
            ).with_for_update().first()

            if not mat_stock:
                mat_stock = models.StockMaster(item_cd=component.child_cd, wh_cd=prod.wh_cd, curr_qty=0.0)
                db.add(mat_stock)
            
            # 실시간 자재 차감 실행
            mat_stock.curr_qty -= total_req_qty
            consumed_materials.append({
                "material_cd": component.child_cd, 
                "consumed_qty": total_req_qty
            })

        # [Step 4] 생산 실적 이력(History) 테이블 저장
        prod_history = models.ProductionResult(
            work_date=prod.work_date,
            line_cd=prod.line_cd,
            item_cd=prod.item_cd,
            prod_qty=prod.prod_qty
        )
        db.add(prod_history)
        
        # 2. 모든 데이터 처리가 정상 완료되었을 때만 MS SQL에 영구 반영 (COMMIT)
        db.commit()
        
    except Exception as e:
        # 오류 발생 시 완벽하게 이진 상태로 복구 (ROLLBACK)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"MS SQL 데이터 처리 중 트랜잭션 오류가 발생하여 안전하게 롤백되었습니다: {str(e)}"
        )

    return {
        "status": "SUCCESS",
        "message": "MS SQL 통합 트랜잭션 완결 완료 (생산 반영 및 자재 수불 차감 완료)",
        "production_qty": prod.prod_qty,
        "consumed_materials": consumed_materials
    }


@app.get("/", response_class=HTMLResponse, tags=["UI 화면"])
def read_dashboard():
    # 프로젝트 루트에 생성할 index.html 파일을 읽어서 웹 브라우저에 뿌려줍니다.
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>index.html 파일을 찾을 수 없습니다. 프로젝트 루트 폴더에 생성해 주세요.</h3>"