from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, VARCHAR, NVARCHAR, CHAR, func
from sqlalchemy.orm import relationship
from database import Base

# 1. 기준정보 - 품목 마스터 (MS SQL 가변길이/유니코드 대응)
class ItemMaster(Base):
    __tablename__ = 'ERP_ITEM_MASTER'

    item_cd = Column(VARCHAR(20), primary_key=True, index=True, comment="품목코드")
    item_nm = Column(NVARCHAR(100), nullable=False, comment="품목명(국문/영문 유니코드)")
    item_typ = Column(CHAR(1), nullable=False, comment="품목구분 (M:자재, P:제품)")
    spec = Column(NVARCHAR(100), comment="규격/사양")
    uom = Column(VARCHAR(10), default='PCS', comment="단위")
    use_flg = Column(CHAR(1), default='Y', comment="사용여부")
    ins_date = Column(DateTime, default=func.now(), comment="등록일시")
    upd_date = Column(DateTime, default=func.now(), onupdate=func.now(), comment="수정일시")

    bom_parents = relationship("BomStructure", foreign_keys="[BomStructure.parent_cd]", back_populates="parent_item")

# 2. BOM 관리 - 복합키 구조 (Clustered Index 자동 생성 유도)
class BomStructure(Base):
    __tablename__ = 'ERP_BOM_STRUCTURE'

    parent_cd = Column(VARCHAR(20), ForeignKey('ERP_ITEM_MASTER.item_cd'), primary_key=True, comment="모품목코드")
    child_cd = Column(VARCHAR(20), ForeignKey('ERP_ITEM_MASTER.item_cd'), primary_key=True, comment="자품목코드")
    seq = Column(Integer, default=1, comment="투입순번")
    req_qty = Column(Float, default=1.0, comment="소요량")
    use_flg = Column(CHAR(1), default='Y', comment="사용여부")

    parent_item = relationship("ItemMaster", foreign_keys=[parent_cd], back_populates="bom_parents")

# 3. 재고관리 - 실시간 현재고 마스터 (MS SQL 복합 Clustered Index 필수)
class StockMaster(Base):
    __tablename__ = 'ERP_STOCK_MASTER'

    item_cd = Column(VARCHAR(20), ForeignKey('ERP_ITEM_MASTER.item_cd'), primary_key=True, comment="품목코드")
    wh_cd = Column(VARCHAR(10), primary_key=True, comment="창고코드")
    curr_qty = Column(Float, default=0.0, comment="현재고수량")
    upd_date = Column(DateTime, default=func.now(), onupdate=func.now())

# 4. 생산관리 - 작업일보 실적 마스터 (자동 증가 Identity 매핑)
class ProductionResult(Base):
    __tablename__ = 'ERP_PRODUCTION_RESULT'

    # MS SQL의 IDENTITY(1,1)에 매핑됩니다.
    prod_id = Column(Integer, primary_key=True, autoincrement=True, comment="실적 고유 ID")
    work_date = Column(VARCHAR(8), nullable=False, index=True, comment="작업일자(YYYYMMDD)")
    line_cd = Column(VARCHAR(10), nullable=False, comment="라인코드")
    item_cd = Column(VARCHAR(20), ForeignKey('ERP_ITEM_MASTER.item_cd'), nullable=False, comment="생산제품코드")
    prod_qty = Column(Float, default=0.0, comment="생산 수량")
    ins_date = Column(DateTime, default=func.now())