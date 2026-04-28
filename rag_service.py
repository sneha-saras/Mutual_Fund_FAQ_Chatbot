"""
RAG Service - Retrieval Augmented Generation
Uses ChromaDB for vector storage and Gemini for embeddings
"""

import os
import chromadb
from chromadb.config import Settings
import google.generativeai as genai
from typing import List, Dict, Optional
import json
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DEFAULT_GEMINI_EMBEDDING_MODEL = os.getenv(
    "GEMINI_EMBEDDING_MODEL",
    # Available for many keys; confirm via `genai.list_models()` with embedContent support
    "models/gemini-embedding-001",
)


class RAGService:
    """
    RAG Service for semantic search and context retrieval
    Uses Gemini embeddings and ChromaDB for vector storage
    """
    
    def __init__(self, db_path: str = "mutual_funds.db", persist_directory: str = "./chroma_db"):
        self.db_path = db_path
        self.persist_directory = persist_directory
        
        # Initialize Gemini
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
            self.embedding_model = DEFAULT_GEMINI_EMBEDDING_MODEL
            self.enabled = True
            print("✓ RAG Service initialized with Gemini embeddings")
        else:
            self.enabled = False
            print("⚠️  RAG Service: No Gemini API key found")
            return
        
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collections
        self.faq_collection = self._get_or_create_collection("faqs")
        self.fund_collection = self._get_or_create_collection("funds")
        
    def _get_or_create_collection(self, name: str):
        """Get or create a ChromaDB collection"""
        try:
            collection = self.client.get_collection(name=name)
            print(f"✓ Loaded existing collection: {name}")
        except:
            collection = self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"✓ Created new collection: {name}")
        return collection
    
    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding using Gemini"""
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None
    
    def _get_query_embedding(self, text: str) -> List[float]:
        """Generate query embedding using Gemini"""
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text,
                task_type="retrieval_query"
            )
            return result['embedding']
        except Exception as e:
            print(f"Error generating query embedding: {e}")
            return None
    
    def index_faqs(self, force_reindex: bool = False):
        """
        Index all FAQs from the database into ChromaDB
        """
        if not self.enabled:
            print("⚠️  RAG not enabled - skipping indexing")
            return False
        
        # Check if already indexed
        if self.faq_collection.count() > 0 and not force_reindex:
            print(f"✓ FAQs already indexed ({self.faq_collection.count()} documents)")
            return True
        
        # Clear existing if force reindex
        if force_reindex and self.faq_collection.count() > 0:
            self.client.delete_collection("faqs")
            self.faq_collection = self._get_or_create_collection("faqs")
            print("🔄 Cleared existing FAQs for re-indexing")
        
        print("📚 Indexing FAQs from database...")
        
        # Get all FAQs from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get funds with their FAQs
        cursor.execute("""
            SELECT f.fund_name, faq.question, faq.answer
            FROM funds f
            INNER JOIN faqs faq ON f.id = faq.fund_id
            WHERE f.fund_name IS NOT NULL
        """)
        rows = cursor.fetchall()
        conn.close()
        
        documents = []
        metadatas = []
        ids = []
        embeddings = []
        
        faq_id = 0
        for fund_name, question, answer in rows:
            # Combine question and answer for better context
            text = f"Question: {question}\nAnswer: {answer}"
            
            # Generate embedding
            embedding = self._get_embedding(text)
            if embedding is None:
                continue
            
            documents.append(text)
            metadatas.append({
                "fund_name": fund_name,
                "question": question,
                "answer": answer,
                "type": "faq"
            })
            ids.append(f"faq_{faq_id}")
            embeddings.append(embedding)
            faq_id += 1
        
        # Add to ChromaDB
        if documents:
            self.faq_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings
            )
            print(f"✅ Indexed {len(documents)} FAQs into vector database")
            return True
        else:
            print("❌ No FAQs found to index")
            return False
    
    def index_funds(self, force_reindex: bool = False):
        """
        Index all fund information into ChromaDB
        """
        if not self.enabled:
            print("⚠️  RAG not enabled - skipping indexing")
            return False
        
        # Check if already indexed
        if self.fund_collection.count() > 0 and not force_reindex:
            print(f"✓ Funds already indexed ({self.fund_collection.count()} documents)")
            return True
        
        # Clear existing if force reindex
        if force_reindex and self.fund_collection.count() > 0:
            self.client.delete_collection("funds")
            self.fund_collection = self._get_or_create_collection("funds")
            print("🔄 Cleared existing funds for re-indexing")
        
        print("📊 Indexing funds from database...")
        
        # Get all funds from database with their returns
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f.id, f.fund_name, f.expense_ratio, f.minimum_sip, f.minimum_lumpsum,
                   f.fund_manager, f.riskometer, f.aum, f.exit_load, f.benchmark,
                   GROUP_CONCAT(r.period || ': ' || r.return_value, ', ') as returns
            FROM funds f
            LEFT JOIN returns r ON f.id = r.fund_id
            WHERE f.fund_name IS NOT NULL
            GROUP BY f.id
        """)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        documents = []
        metadatas = []
        ids = []
        embeddings = []
        
        for row in rows:
            fund = dict(zip(columns, row))
            
            # Create rich text description
            text_parts = [
                f"Fund Name: {fund['fund_name']}"
            ]
            
            if fund.get('fund_manager'):
                text_parts.append(f"Fund Manager: {fund['fund_manager']}")
            if fund.get('expense_ratio'):
                text_parts.append(f"Expense Ratio: {fund['expense_ratio']}")
            if fund.get('riskometer'):
                text_parts.append(f"Risk Level: {fund['riskometer']}")
            
            # Add returns
            if fund.get('returns'):
                text_parts.append(f"Returns: {fund['returns']}")
            
            # Add AUM
            if fund.get('aum'):
                text_parts.append(f"AUM: {fund['aum']}")
            
            # Add benchmark
            if fund.get('benchmark'):
                text_parts.append(f"Benchmark: {fund['benchmark']}")
            
            # Add minimums
            if fund.get('minimum_sip'):
                text_parts.append(f"Minimum SIP: {fund['minimum_sip']}")
            if fund.get('minimum_lumpsum'):
                text_parts.append(f"Minimum Lumpsum: {fund['minimum_lumpsum']}")
            
            text = "\n".join(text_parts)
            
            # Generate embedding
            embedding = self._get_embedding(text)
            if embedding is None:
                continue
            
            documents.append(text)
            metadatas.append({
                "fund_name": fund['fund_name'],
                "fund_manager": fund.get('fund_manager') or "",
                "expense_ratio": fund.get('expense_ratio') or "",
                "riskometer": fund.get('riskometer') or "",
                "benchmark": fund.get('benchmark') or "",
                "type": "fund"
            })
            ids.append(f"fund_{fund['fund_name']}")
            embeddings.append(embedding)
        
        # Add to ChromaDB
        if documents:
            self.fund_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings
            )
            print(f"✅ Indexed {len(documents)} funds into vector database")
            return True
        else:
            print("❌ No funds found to index")
            return False
    
    def search_faqs(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        Search FAQs using semantic similarity
        """
        if not self.enabled:
            return []
        
        # Generate query embedding
        query_embedding = self._get_query_embedding(query)
        if query_embedding is None:
            return []
        
        # Search in ChromaDB
        results = self.faq_collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self.faq_collection.count())
        )
        
        # Format results
        formatted_results = []
        if results and results['metadatas'] and len(results['metadatas']) > 0:
            for i, metadata in enumerate(results['metadatas'][0]):
                formatted_results.append({
                    "question": metadata['question'],
                    "answer": metadata['answer'],
                    "fund_name": metadata['fund_name'],
                    "relevance_score": 1 - results['distances'][0][i] if results['distances'] else 1.0
                })
        
        return formatted_results
    
    def search_funds(self, query: str, n_results: int = 3) -> List[Dict]:
        """
        Search funds using semantic similarity
        """
        if not self.enabled:
            return []
        
        # Generate query embedding
        query_embedding = self._get_query_embedding(query)
        if query_embedding is None:
            return []
        
        # Search in ChromaDB
        results = self.fund_collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self.fund_collection.count())
        )
        
        # Format results
        formatted_results = []
        if results and results['metadatas'] and len(results['metadatas']) > 0:
            for i, metadata in enumerate(results['metadatas'][0]):
                formatted_results.append({
                    "fund_name": metadata['fund_name'],
                    "fund_manager": metadata['fund_manager'],
                    "expense_ratio": metadata['expense_ratio'],
                    "riskometer": metadata['riskometer'],
                    "benchmark": metadata.get('benchmark', ''),
                    "relevance_score": 1 - results['distances'][0][i] if results['distances'] else 1.0
                })
        
        return formatted_results
    
    def get_relevant_context(self, query: str, n_faqs: int = 3, n_funds: int = 2) -> str:
        """
        Get relevant context for a query by combining FAQs and fund info
        """
        context_parts = []
        
        # Search FAQs
        faqs = self.search_faqs(query, n_results=n_faqs)
        if faqs:
            context_parts.append("📋 Relevant FAQs:")
            for i, faq in enumerate(faqs, 1):
                context_parts.append(f"\n{i}. Fund: {faq['fund_name']}")
                context_parts.append(f"   Q: {faq['question']}")
                context_parts.append(f"   A: {faq['answer']}")
        
        # Search Funds
        funds = self.search_funds(query, n_results=n_funds)
        if funds:
            context_parts.append("\n\n💼 Relevant Funds:")
            for i, fund in enumerate(funds, 1):
                context_parts.append(f"\n{i}. {fund['fund_name']}")
                context_parts.append(f"   Manager: {fund['fund_manager']}")
                context_parts.append(f"   Expense Ratio: {fund['expense_ratio']}")
                context_parts.append(f"   Risk: {fund['riskometer']}")
        
        return "\n".join(context_parts) if context_parts else "No relevant context found."
    
    def reset(self):
        """Reset all collections"""
        if self.enabled:
            self.client.reset()
            print("✓ ChromaDB reset complete")


# Initialize global RAG service
rag_service = RAGService()


if __name__ == "__main__":
    # Test the RAG service
    print("\n" + "="*60)
    print("🚀 Testing RAG Service")
    print("="*60 + "\n")
    
    # Index data
    rag_service.index_faqs(force_reindex=True)
    rag_service.index_funds(force_reindex=True)
    
    # Test queries
    test_queries = [
        "What is the minimum SIP amount?",
        "Tell me about mid cap funds",
        "Which fund has the best returns?",
        "What is expense ratio?"
    ]
    
    print("\n" + "="*60)
    print("🔍 Testing Semantic Search")
    print("="*60 + "\n")
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        print("-" * 60)
        context = rag_service.get_relevant_context(query, n_faqs=2, n_funds=1)
        print(context)
        print()
