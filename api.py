"""
FastAPI Backend for INDMoney FAQ Assistant
Provides REST API for mutual fund data and FAQ search
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from data_storage import DataStorage
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="INDMoney FAQ Assistant API",
    description="REST API for mutual fund information and FAQ search",
    version="1.0.0"
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize storage
storage = DataStorage()

# Gemini + RAG (optional: heavy deps or missing GEMINI_API_KEY)
gemini = None
try:
    from gemini_service import gemini
except ImportError as e:
    print(f"Warning: gemini_service not importable, AI routes disabled: {e}")

AI_AVAILABLE = bool(gemini and getattr(gemini, "enabled", False))

# Pydantic models
class Fund(BaseModel):
    id: int
    fund_name: str
    source_url: str
    expense_ratio: Optional[str] = None
    exit_load: Optional[str] = None
    minimum_sip: Optional[str] = None
    minimum_lumpsum: Optional[str] = None
    fund_manager: Optional[str] = None
    benchmark: Optional[str] = None
    riskometer: Optional[str] = None
    returns: Dict[str, str] = {}
    
class FundDetail(Fund):
    holdings: List[Dict[str, Any]] = []
    faqs: List[Dict[str, str]] = []
    table_data: Dict[str, str] = {}
    scraped_at: Optional[str] = None

class FAQ(BaseModel):
    question: str
    answer: str
    fund_name: Optional[str] = None
    source_url: Optional[str] = None

class AskQuestion(BaseModel):
    question: str
    use_context: bool = True
    use_rag: bool = True

class InvestmentProfile(BaseModel):
    amount: int
    risk_appetite: str  # low, moderate, high
    duration: str  # short, medium, long


# API Endpoints
@app.get("/")
def read_root():
    """API health check and info"""
    endpoints: Dict[str, str] = {
        "funds": "/api/funds",
        "fund_detail": "/api/funds/{fund_id}",
        "search": "/api/search",
        "faq": "/api/faq",
        "compare": "/api/compare",
        "stats": "/api/stats",
    }
    if gemini is not None:
        endpoints["ai_ask"] = "/api/ai/ask"
        endpoints["ai_compare"] = "/api/ai/compare"
        endpoints["ai_advice"] = "/api/ai/advice"
        endpoints["ai_explain"] = "/api/ai/explain"
    return {
        "message": "INDMoney FAQ Assistant API",
        "version": "1.0.0",
        "ai_available": AI_AVAILABLE,
        "gemini_module_loaded": gemini is not None,
        "endpoints": endpoints,
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        }
    }


@app.get("/api/funds", response_model=List[Fund])
def get_funds(
    limit: int = Query(10, ge=1, le=100),
    category: Optional[str] = None
):
    """Get list of all mutual funds"""
    try:
        conn = sqlite3.connect(storage.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Build query
        query = "SELECT * FROM funds"
        params = []
        
        if category:
            query += " WHERE fund_name LIKE ?"
            params.append(f"%{category}%")
        
        query += " ORDER BY fund_name LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        funds = []
        
        for row in cursor.fetchall():
            fund_dict = dict(row)
            
            # Get returns
            cursor.execute('SELECT period, return_value FROM returns WHERE fund_id = ?', (row['id'],))
            fund_dict['returns'] = {r['period']: r['return_value'] for r in cursor.fetchall()}
            
            funds.append(fund_dict)
        
        conn.close()
        return funds
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/funds/{fund_id}", response_model=FundDetail)
def get_fund_detail(fund_id: int):
    """Get detailed information about a specific fund"""
    try:
        conn = sqlite3.connect(storage.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get fund
        cursor.execute('SELECT * FROM funds WHERE id = ?', (fund_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Fund not found")
        
        fund_dict = dict(row)
        
        # Get returns
        cursor.execute('SELECT period, return_value FROM returns WHERE fund_id = ?', (fund_id,))
        fund_dict['returns'] = {r['period']: r['return_value'] for r in cursor.fetchall()}
        
        # Get holdings
        cursor.execute('SELECT holding_name as name, allocation, sector FROM holdings WHERE fund_id = ?', (fund_id,))
        fund_dict['holdings'] = [dict(h) for h in cursor.fetchall()]
        
        # Get FAQs
        cursor.execute('SELECT question, answer FROM faqs WHERE fund_id = ?', (fund_id,))
        fund_dict['faqs'] = [dict(f) for f in cursor.fetchall()]
        
        # Parse table_data if stored as JSON string
        nav = cursor.execute('SELECT nav, aum FROM funds WHERE id = ?', (fund_id,)).fetchone()
        fund_dict['table_data'] = {
            'NAV': nav['nav'] if nav['nav'] else 'N/A',
            'AUM': nav['aum'] if nav['aum'] else 'N/A'
        }
        
        conn.close()
        return fund_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search")
def search_funds(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50)
):
    """Search funds by name or other attributes"""
    try:
        conn = sqlite3.connect(storage.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Search in fund name, fund manager, or category
        cursor.execute('''
            SELECT DISTINCT f.* FROM funds f
            WHERE f.fund_name LIKE ? 
               OR f.fund_manager LIKE ?
               OR f.benchmark LIKE ?
            LIMIT ?
        ''', (f'%{q}%', f'%{q}%', f'%{q}%', limit))
        
        results = []
        for row in cursor.fetchall():
            fund_dict = dict(row)
            
            # Get returns
            cursor.execute('SELECT period, return_value FROM returns WHERE fund_id = ?', (row['id'],))
            fund_dict['returns'] = {r['period']: r['return_value'] for r in cursor.fetchall()}
            
            results.append(fund_dict)
        
        conn.close()
        return {"results": results, "count": len(results)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/faq", response_model=List[FAQ])
def search_faq(
    q: str = Query(..., min_length=1, description="FAQ search query"),
    limit: int = Query(5, ge=1, le=20)
):
    """Search FAQs across all funds"""
    try:
        conn = sqlite3.connect(storage.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Search FAQs
        cursor.execute('''
            SELECT f.question, f.answer, fu.fund_name, fu.source_url
            FROM faqs f
            JOIN funds fu ON f.fund_id = fu.id
            WHERE f.question LIKE ? OR f.answer LIKE ?
            LIMIT ?
        ''', (f'%{q}%', f'%{q}%', limit))
        
        faqs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return faqs
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/compare")
def compare_funds(fund_ids: str = Query(..., description="Comma-separated fund IDs")):
    """Compare multiple funds"""
    try:
        ids = [int(id.strip()) for id in fund_ids.split(',')]
        
        if len(ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 funds required for comparison")
        
        if len(ids) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 funds can be compared")
        
        conn = sqlite3.connect(storage.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        funds = []
        for fund_id in ids:
            cursor.execute('SELECT * FROM funds WHERE id = ?', (fund_id,))
            row = cursor.fetchone()
            
            if row:
                fund_dict = dict(row)
                
                # Get returns
                cursor.execute('SELECT period, return_value FROM returns WHERE fund_id = ?', (fund_id,))
                fund_dict['returns'] = {r['period']: r['return_value'] for r in cursor.fetchall()}
                
                funds.append(fund_dict)
        
        conn.close()
        
        if not funds:
            raise HTTPException(status_code=404, detail="No funds found")
        
        return {"funds": funds, "count": len(funds)}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fund IDs")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
def get_stats():
    """Get database statistics"""
    try:
        conn = sqlite3.connect(storage.db_path)
        cursor = conn.cursor()
        
        # Count funds
        cursor.execute('SELECT COUNT(*) as count FROM funds')
        total_funds = cursor.fetchone()[0]
        
        # Count FAQs
        cursor.execute('SELECT COUNT(*) as count FROM faqs')
        total_faqs = cursor.fetchone()[0]
        
        # Get fund categories
        cursor.execute('SELECT fund_name FROM funds WHERE fund_name IS NOT NULL')
        funds = cursor.fetchall()
        
        categories = {}
        for fund in funds:
            name = fund[0].lower()
            if 'large' in name:
                categories['Large Cap'] = categories.get('Large Cap', 0) + 1
            elif 'mid' in name:
                categories['Mid Cap'] = categories.get('Mid Cap', 0) + 1
            elif 'small' in name:
                categories['Small Cap'] = categories.get('Small Cap', 0) + 1
        
        conn.close()
        
        return {
            "total_funds": total_funds,
            "total_faqs": total_faqs,
            "categories": categories,
            "database": storage.db_path,
            "ai_available": AI_AVAILABLE
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ AI Endpoints (gemini_service + optional RAG) ============
if gemini is not None:
    @app.post("/api/ai/ask")
    def ai_ask_question(request: AskQuestion):
        """Ask a question and get AI-powered answer (RAG when indexed + enabled)."""
        q = (request.question or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="question is required")
        return gemini.answer_question(
            q,
            use_context=request.use_context,
            use_rag=request.use_rag,
        )

    @app.get("/api/ai/compare")
    def ai_compare_funds(
        funds: str = Query(..., description="Comma-separated fund names")
    ):
        """Compare funds using AI analysis"""
        names = [f.strip() for f in funds.split(",") if f.strip()]
        if len(names) < 2:
            raise HTTPException(
                status_code=400,
                detail="Provide at least two comma-separated fund names",
            )
        return gemini.compare_funds(names)

    @app.post("/api/ai/advice")
    def ai_investment_advice(profile: InvestmentProfile):
        """Get personalized investment advice using AI"""
        return gemini.get_investment_advice(
            profile.amount,
            profile.risk_appetite,
            profile.duration,
        )

    @app.get("/api/ai/explain")
    def ai_explain_term(term: str = Query(..., description="Term to explain")):
        """Explain a mutual fund term using AI"""
        return gemini.explain_term(term)