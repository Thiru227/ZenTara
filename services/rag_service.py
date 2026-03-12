import os
import logging
import json

logger = logging.getLogger(__name__)


def get_or_create_collection(carrier_slug, collections_path):
    """Get or create a ChromaDB collection for a carrier."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(collections_path, f"carrier_{carrier_slug}"))
        collection = client.get_or_create_collection(
            name=f"carrier_{carrier_slug}",
            metadata={"description": f"SLA documents for {carrier_slug}"}
        )
        return collection
    except ImportError:
        logger.warning("ChromaDB not installed, using in-memory fallback")
        return None
    except Exception as e:
        logger.error(f"ChromaDB error: {e}")
        return None


def ingest_document(carrier_slug, sla_document_id, pages, metadata, collections_path):
    """Ingest PDF pages into carrier's ChromaDB collection."""
    collection = get_or_create_collection(carrier_slug, collections_path)
    if not collection:
        logger.warning(f"No ChromaDB collection available for {carrier_slug}")
        return False

    try:
        # Chunk text into manageable pieces
        chunks = []
        for page in pages:
            page_text = page.get('text', '').strip()
            if not page_text:
                continue
            # Split long pages into ~500 word chunks
            words = page_text.split()
            chunk_size = 500
            for i in range(0, len(words), chunk_size):
                chunk_words = words[i:i + chunk_size]
                chunk_text = ' '.join(chunk_words)
                if len(chunk_text) > 50:  # Skip tiny chunks
                    chunks.append({
                        'text': chunk_text,
                        'page_number': page.get('page_number', 1),
                        'chunk_index': i // chunk_size
                    })

        if not chunks:
            return False

        # Add chunks to ChromaDB
        ids = [f"{carrier_slug}_{sla_document_id}_page{c['page_number']}_chunk{c['chunk_index']}" for c in chunks]
        texts = [c['text'] for c in chunks]
        metadatas = [{
            **metadata,
            'page_number': c['page_number'],
            'chunk_index': c['chunk_index']
        } for c in chunks]

        # Add in batches to avoid size limits
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            collection.add(
                ids=ids[i:i + batch_size],
                documents=texts[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size]
            )

        logger.info(f"Ingested {len(chunks)} chunks for {carrier_slug}")
        return True
    except Exception as e:
        logger.error(f"RAG ingestion error: {e}")
        return False


def query_collection(carrier_slug, query_text, n_results=5, collections_path=None):
    """Query a carrier's collection for relevant chunks."""
    collection = get_or_create_collection(carrier_slug, collections_path)
    if not collection:
        return []

    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=min(n_results, collection.count() or 1)
        )
        
        chunks = []
        if results and results.get('documents'):
            docs = results['documents'][0]
            metas = results.get('metadatas', [[]])[0]
            for doc, meta in zip(docs, metas):
                chunks.append({
                    'text': doc,
                    'page': meta.get('page_number', '?'),
                    'source': meta.get('original_filename', meta.get('sla_version', 'Unknown')),
                    'carrier': meta.get('carrier_id', carrier_slug),
                    'version': meta.get('sla_version', 'v1.0')
                })
        return chunks
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        return []


def query_all_collections(query_text, carrier_slugs, n_results=5, collections_path=None):
    """Query multiple carrier collections and combine results."""
    all_chunks = []
    for slug in carrier_slugs:
        chunks = query_collection(slug, query_text, n_results=3, collections_path=collections_path)
        all_chunks.extend(chunks)
    
    # Return top N results (already ranked by ChromaDB similarity)
    return all_chunks[:n_results]


def delete_document_chunks(carrier_slug, sla_document_id, collections_path):
    """Remove all chunks for a specific SLA document version."""
    collection = get_or_create_collection(carrier_slug, collections_path)
    if not collection:
        return False

    try:
        # Get all IDs for this document
        prefix = f"{carrier_slug}_{sla_document_id}_"
        results = collection.get(where={"sla_document_id": str(sla_document_id)})
        if results and results.get('ids'):
            collection.delete(ids=results['ids'])
        return True
    except Exception as e:
        logger.error(f"ChromaDB delete error: {e}")
        return False
