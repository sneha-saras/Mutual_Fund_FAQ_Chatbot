"""
Minimal Gemini AI Service for Vercel Deployment
Uses Google Gemini (default: gemini-2.5-flash) for responses
"""

# Import with error handling for Vercel deployment
try:
    from google.generativeai.generative_models import GenerativeModel
    GEMINI_AVAILABLE = True
except ImportError:
    GenerativeModel = None
    GEMINI_AVAILABLE = False

from typing import List, Dict, Optional
import os
from data_storage import DataStorage
import sqlite3

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiService:
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini service
        Get your free API key from: https://makersuite.google.com/app/apikey
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        if not self.api_key or not GEMINI_AVAILABLE:
            print("⚠️  Warning: GEMINI_API_KEY not set or Gemini not available.")
            self.enabled = False
            self.model = None
            self.model_name = ""
        else:
            try:
                # Use Gemini 2.0 Flash - fastest and free
                if GenerativeModel is not None:
                    self.model_name = DEFAULT_GEMINI_MODEL
                    self.model = GenerativeModel(self.model_name)
                    self.enabled = True
                    print(f"✓ Gemini initialized ({self.model_name})")
                else:
                    self.enabled = False
                    self.model = None
                    self.model_name = ""
            except Exception as e:
                print(f"⚠️  Warning: Failed to initialize Gemini: {e}")
                self.enabled = False
                self.model = None
                self.model_name = ""
        
        self.storage = DataStorage()
    
    def get_fund_context(self, query: str = "") -> str:
        """Get relevant fund data as context for Gemini"""
        try:
            conn = sqlite3.connect(self.storage.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all funds with complete data
            cursor.execute('''
                SELECT f.*, GROUP_CONCAT(r.period || ': ' || r.return_value) as returns_text
                FROM funds f
                LEFT JOIN returns r ON f.id = r.fund_id
                WHERE f.fund_name IS NOT NULL
                GROUP BY f.id
            ''')
            
            funds = cursor.fetchall()
            
            # Build context
            context = "Available Mutual Funds Information:\n\n"
            
            for fund in funds:
                context += f"Fund: {fund['fund_name']}\n"
                if fund['expense_ratio']:
                    context += f"  - Expense Ratio: {fund['expense_ratio']}\n"
                if fund['minimum_sip']:
                    context += f"  - Minimum SIP: {fund['minimum_sip']}\n"
                if fund['minimum_lumpsum']:
                    context += f"  - Minimum Lumpsum: {fund['minimum_lumpsum']}\n"
                if fund['fund_manager']:
                    context += f"  - Fund Manager: {fund['fund_manager']}\n"
                if fund['riskometer']:
                    context += f"  - Risk Level: {fund['riskometer']}\n"
                if fund['returns_text']:
                    context += f"  - Returns: {fund['returns_text']}\n"
                if fund['exit_load']:
                    context += f"  - Exit Load: {fund['exit_load']}\n"
                
                # Get FAQs for this fund
                cursor.execute('SELECT question, answer FROM faqs WHERE fund_id = ?', (fund['id'],))
                faqs = cursor.fetchall()
                if faqs:
                    context += "  - FAQs:\n"
                    for faq in faqs:
                        context += f"    Q: {faq['question']}\n"
                        context += f"    A: {faq['answer']}\n"
                
                context += "\n"
            
            conn.close()
            return context
            
        except Exception as e:
            print(f"Error getting fund context: {e}")
            return ""
    
    def answer_question(self, question: str, use_context: bool = True) -> Dict:
        """
        Answer a question using Gemini
        
        Args:
            question: User's question
            use_context: Whether to use fund context
        
        Returns: {answer, source, confidence, model}
        """
        if not self.enabled or self.model is None:
            return {
                "answer": "Gemini AI is not configured. Please set GEMINI_API_KEY in your .env file.",
                "source": "error",
                "confidence": "low",
                "model": "none"
            }
        
        try:
            # Build prompt
            if use_context:
                context = self.get_fund_context()
                
                prompt = f"""You are a helpful HDFC Mutual Funds specialist at INDMoney.
You help investors understand and invest in HDFC mutual funds.

{context}

User Question: {question}

Instructions:
- Provide clear, helpful answers focusing on HDFC funds
- Use simple bullet points with • symbol (not asterisks or markdown)
- Be polite and professional
- If exact data is unavailable, provide information about similar HDFC funds that ARE available
- Use specific data from the available HDFC funds
- When comparing funds, mention key metrics (returns, expense ratio, risk)
- Keep response under 200 words
- Use ₹ symbol for rupees
- Always be helpful - avoid saying "I cannot answer" unless absolutely no relevant information exists
- Do NOT use markdown formatting (* or ** or #)
- Use plain text with • for bullet points

Answer:"""
            else:
                prompt = f"""You are a helpful mutual fund investment assistant.
Answer the following question about mutual fund investing.

Question: {question}

Provide a clear, helpful answer in under 150 words."""
            
            # Generate response
            response = self.model.generate_content(prompt)
            answer_text = response.text.strip()
            
            return {
                "answer": answer_text,
                "source": self.model_name,
                "confidence": "high",
                "model": self.model_name
            }
            
        except Exception as e:
            return {
                "answer": f"Error generating answer: {str(e)}",
                "source": "error",
                "confidence": "low",
                "model": "none"
            }
    
    def compare_funds(self, fund_names: List[str]) -> Dict:
        """Compare multiple funds using Gemini"""
        if not self.enabled or self.model is None:
            return {
                "comparison": "Gemini AI is not configured.",
                "source": "error"
            }
        
        try:
            # For comparison, get context for all mentioned funds
            context = self.get_fund_context()
            
            prompt = f"""You are a mutual fund investment analyst.
Compare the following mutual funds based on the data provided.

{context}

Funds to compare: {', '.join(fund_names)}

Provide a detailed comparison covering:
1. Returns (1Y, 3Y, 5Y)
2. Expense Ratio
3. Risk Level
4. Minimum Investment
5. Your recommendation based on different investor profiles

Format the response in a clear, structured way."""
            
            response = self.model.generate_content(prompt)
            
            return {
                "comparison": response.text.strip(),
                "source": self.model_name,
                "model": self.model_name
            }
            
        except Exception as e:
            return {
                "comparison": f"Error generating comparison: {str(e)}",
                "source": "error"
            }
    
    def get_investment_advice(self, 
                            amount: int, 
                            risk_appetite: str, 
                            duration: str) -> Dict:
        """Get personalized investment advice"""
        if not self.enabled or self.model is None:
            return {
                "advice": "Gemini AI is not configured.",
                "source": "error"
            }
        
        try:
            # Get context for investment advice query
            context = self.get_fund_context()
            
            prompt = f"""You are a certified mutual fund investment advisor.

Available Funds:
{context}

Client Profile:
- Investment Amount: ₹{amount:,}
- Risk Appetite: {risk_appetite}
- Investment Duration: {duration}

Based on the available funds and the client's profile, provide:
1. Recommended fund allocation (which funds and what percentage)
2. Reasoning for the recommendation
3. Expected returns (realistic estimate)
4. Important considerations/warnings

Be specific and use actual fund data."""
            
            response = self.model.generate_content(prompt)
            
            return {
                "advice": response.text.strip(),
                "source": self.model_name,
                "model": self.model_name
            }
            
        except Exception as e:
            return {
                "advice": f"Error generating advice: {str(e)}",
                "source": "error"
            }
    
    def explain_term(self, term: str) -> Dict:
        """Explain mutual fund terminology"""
        if not self.enabled or self.model is None:
            return {
                "explanation": "Gemini AI is not configured.",
                "source": "error"
            }
        
        try:
            prompt = f"""Explain the following mutual fund term in simple language that a beginner can understand:

Term: {term}

Provide:
1. Simple definition
2. Real-world example
3. Why it matters for investors

Keep it concise (under 150 words) and easy to understand."""
            
            response = self.model.generate_content(prompt)
            
            return {
                "explanation": response.text.strip(),
                "term": term,
                "source": self.model_name,
                "model": self.model_name
            }
            
        except Exception as e:
            return {
                "explanation": f"Error generating explanation: {str(e)}",
                "source": "error"
            }