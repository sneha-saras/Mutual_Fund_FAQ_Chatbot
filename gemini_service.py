"""
Gemini AI Service for Intelligent FAQ Answering
Uses Google Gemini (default: gemini-2.5-flash) for responses
NOW WITH RAG - Retrieval Augmented Generation
"""

import google.generativeai as genai
from typing import List, Dict, Optional
import os
import re
from data_storage import DataStorage
import sqlite3
from rag_service import rag_service

# Must be a model your key can call (see https://ai.google.dev/gemini-api/docs/models )
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiService:
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini service
        Get your free API key from: https://makersuite.google.com/app/apikey
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        if not self.api_key:
            print("⚠️  Warning: GEMINI_API_KEY not set. Set it in .env file or environment variable.")
            self.enabled = False
            self.model = None
            self.model_name = ""
        else:
            try:
                genai.configure(api_key=self.api_key)
                self.model_name = DEFAULT_GEMINI_MODEL
                self.model = genai.GenerativeModel(self.model_name)
                self.enabled = True
                print(f"✓ Gemini initialized ({self.model_name})")
            except Exception as e:
                print(f"⚠️  Warning: Failed to initialize Gemini: {e}")
                self.enabled = False
                self.model = None
                self.model_name = ""
        
        self.storage = DataStorage()
    
    def _extract_fund_sources(self, context: str, question: str) -> List[Dict]:
        """Extract fund sources with URLs from context"""
        sources = []
        
        # Get fund names from database with URLs
        try:
            conn = sqlite3.connect(self.storage.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT fund_name, source_url
                FROM funds
                WHERE fund_name IS NOT NULL AND source_url IS NOT NULL
            """)
            
            funds = cursor.fetchall()
            conn.close()
            
            # Check which funds are mentioned in context
            for fund in funds:
                if fund['fund_name'].lower() in context.lower():
                    sources.append({
                        "fund_name": fund['fund_name'],
                        "url": fund['source_url']
                    })
        except Exception as e:
            print(f"Error extracting sources: {e}")
        
        return sources
    
    def get_fund_context(self, query: str = "", use_rag: bool = True) -> str:
        """Get relevant fund data as context for Gemini
        
        Args:
            query: User's question (used for RAG semantic search)
            use_rag: Whether to use RAG for context retrieval (default: True)
        """
        # Use RAG for intelligent context retrieval
        if use_rag and query and rag_service.enabled:
            return rag_service.get_relevant_context(query, n_faqs=3, n_funds=2)
        
        # Fallback to old method (get all data)
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
    
    def answer_question(self, question: str, use_context: bool = True, use_rag: bool = True) -> Dict:
        """
        Answer a question using Gemini with RAG
        
        Args:
            question: User's question
            use_context: Whether to use fund context
            use_rag: Whether to use RAG for intelligent context retrieval
        
        Returns: {answer, source, confidence, retrieval_method}
        """
        if not self.enabled:
            return {
                "answer": "Gemini AI is not configured. Please set GEMINI_API_KEY in your .env file.",
                "source": "error",
                "confidence": "low",
                "model": "none",
                "retrieval_method": "none"
            }
        
        try:
            # Build prompt
            context = ""
            retrieval_method = "none"
            if use_context:
                context = self.get_fund_context(query=question, use_rag=use_rag)
                retrieval_method = "rag" if (use_rag and rag_service.enabled) else "full_context"
                
                prompt = f"""You are a helpful mutual fund investment assistant at INDMoney.
You answer using the provided context and avoid guessing.

{context}

User Question: {question}

Instructions:
- Provide clear, beginner-friendly answers
- Use simple bullet points with • symbol (not asterisks or markdown)
- Be polite and professional
- If exact data is unavailable in the provided context, say so briefly and suggest what to check next
- Use specific numbers from the provided context when possible
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
            
            # Extract fund sources from context
            sources = self._extract_fund_sources(context, question)

            # Hard rule: never return model-invented URLs.
            # Keep only URLs that come from the DB source list.
            allowed_urls = { (s.get("url") or "").strip() for s in (sources or []) }
            allowed_urls.discard("")
            if allowed_urls:
                url_re = re.compile(r"https?://\\S+")
                found_urls = set(url_re.findall(answer_text))
                for url in found_urls:
                    if url not in allowed_urls:
                        answer_text = answer_text.replace(url, "")
            else:
                # If we don't have any trusted sources, strip all URLs.
                answer_text = re.sub(r"https?://\\S+", "", answer_text)

            # Prefer real URLs from DB over model-made "Sources:" text.
            if sources:
                sources_lines = ["", "Sources:"]
                for s in sources:
                    name = (s.get("fund_name") or "").strip()
                    url = (s.get("url") or "").strip()
                    if name and url:
                        sources_lines.append(f"• {name}: {url}")
                if len(sources_lines) > 2:
                    answer_text = answer_text + "\n" + "\n".join(sources_lines)
            
            return {
                "answer": answer_text,
                "source": self.model_name,
                "confidence": "high",
                "model": self.model_name,
                "retrieval_method": retrieval_method,
                "fund_sources": sources
            }
            
        except Exception as e:
            return {
                "answer": f"Error generating answer: {str(e)}",
                "source": "error",
                "confidence": "low",
                "model": "none",
                "retrieval_method": "error"
            }
    
    def compare_funds(self, fund_names: List[str]) -> Dict:
        """Compare multiple funds using Gemini with RAG"""
        if not self.enabled:
            return {
                "comparison": "Gemini AI is not configured.",
                "source": "error"
            }
        
        try:
            # For comparison, get context for all mentioned funds
            context = self.get_fund_context(query=' '.join(fund_names), use_rag=True)
            
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
        if not self.enabled:
            return {
                "advice": "Gemini AI is not configured.",
                "source": "error"
            }
        
        try:
            # Get context for investment advice query
            query = f"investment advice {risk_appetite} risk {duration} duration"
            context = self.get_fund_context(query=query, use_rag=True)
            
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
        if not self.enabled:
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


# Shared instance for API and scripts
gemini = GeminiService()


# Test the service
if __name__ == "__main__":
    import sys
    
    print("Testing Gemini Service...")
    print("="*60)
    
    # Check for API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("\n⚠️  GEMINI_API_KEY not found in environment")
        print("\nTo get your free API key:")
        print("1. Visit: https://makersuite.google.com/app/apikey")
        print("2. Create an API key")
        print("3. Set it in .env file:")
        print("   echo 'GEMINI_API_KEY=your_key_here' > .env")
        print("\nOr set it temporarily:")
        print("   export GEMINI_API_KEY=your_key_here")
        sys.exit(1)
    
    if gemini.enabled:
        print("\n✓ Gemini initialized successfully!")
        print("\nTesting question answering...")
        
        result = gemini.answer_question("What is the expense ratio of HDFC Mid Cap fund?")
        print(f"\nQuestion: What is the expense ratio of HDFC Mid Cap fund?")
        print(f"Answer: {result['answer']}")
        print(f"Source: {result['source']}")
        
        print("\n" + "="*60)
        print("✓ Test complete!")
    else:
        print("\n✗ Gemini not initialized")
