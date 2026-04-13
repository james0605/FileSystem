import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

BASE = Path('D:/James8/FileSystem/rag_system')
model = SentenceTransformer('BAAI/bge-base-en-v1.5')
client = chromadb.PersistentClient(path=str(BASE / 'chroma_db'))
col = client.get_collection('documents')

query = 'DRE LETH to GETH forwarding table register setup steps'

emb = model.encode(query, normalize_embeddings=True).tolist()

kwargs = dict(query_embeddings=[emb], n_results=8, include=['documents','metadatas','distances'])
res = col.query(**kwargs)

for doc, meta, dist in zip(res['documents'][0], res['metadatas'][0], res['distances'][0]):
    print(f"[{meta['source']}, Page {meta['page']}] (score={round(1-dist,3)})")
    print(doc.strip())
    print()
