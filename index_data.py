"""
Index FAQs and Funds into Vector Database
Run this script to build the RAG index
"""

import argparse
import sys
from rag_service import rag_service


def main():
    parser = argparse.ArgumentParser(description="Index FAQs and funds into Chroma (RAG).")
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Reindex without interactive prompt (useful for CI or scripts).",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 INDEXING FAQS AND FUNDS INTO VECTOR DATABASE")
    print("=" * 70)
    print()
    
    if not rag_service.enabled:
        print("❌ RAG Service is not enabled")
        print("Please ensure GEMINI_API_KEY is set in your .env file")
        sys.exit(1)
    
    print("📊 Current Status:")
    print(f"   - FAQs indexed: {rag_service.faq_collection.count()}")
    print(f"   - Funds indexed: {rag_service.fund_collection.count()}")
    print()
    
    if rag_service.faq_collection.count() > 0 or rag_service.fund_collection.count() > 0:
        if args.force:
            force_reindex = True
        else:
            response = input("⚠️  Data already indexed. Force reindex? (y/N): ").strip().lower()
            force_reindex = response == 'y'
    else:
        force_reindex = False
    
    print()
    print("🔄 Starting indexing process...")
    print()
    
    # Index FAQs
    print("1️⃣  Indexing FAQs...")
    faq_success = rag_service.index_faqs(force_reindex=force_reindex)
    
    # Index Funds
    print("\n2️⃣  Indexing Funds...")
    fund_success = rag_service.index_funds(force_reindex=force_reindex)
    
    print()
    print("=" * 70)
    if faq_success and fund_success:
        print("✅ INDEXING COMPLETE!")
        print()
        print(f"📋 Total FAQs indexed: {rag_service.faq_collection.count()}")
        print(f"💼 Total Funds indexed: {rag_service.fund_collection.count()}")
        print()
        print("🎉 Your RAG system is ready to use!")
    else:
        print("⚠️  INDEXING INCOMPLETE")
        print("   Check the errors above and try again")
    print("=" * 70)


if __name__ == "__main__":
    main()
