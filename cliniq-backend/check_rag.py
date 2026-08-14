try:
    from rag_engine import RAGEngine
    print('RAG OK')
except Exception as e:
    print('RAG IMPORT ERROR')
    import traceback
    traceback.print_exc()
