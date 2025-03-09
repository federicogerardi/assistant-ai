def get_document_stats(agent_id, config, doc_service):
    """Get statistics for a specific agent's documents."""
    stats = {
        'agent_id': agent_id,
        'name': config['name'],
        'icon': config['icon'],
        'total_documents': 0,
        'total_chunks': 0,
        'avg_chunks_per_doc': 0,
        'last_updated': None,
        'documents': []
    }
    
    if doc_service.table_name in doc_service.db.table_names():
        table = doc_service.db.open_table(doc_service.table_name)
        if 'metadata' in table.schema.names:
            df = table.to_pandas()
            if not df.empty:
                # Collect document statistics
                unique_docs = df['metadata'].apply(lambda x: x['source']).unique()
                stats['total_documents'] = len(unique_docs)
                stats['total_chunks'] = len(df)
                stats['avg_chunks_per_doc'] = (stats['total_chunks'] / 
                                             stats['total_documents'] if 
                                             stats['total_documents'] > 0 else 0)
                
                # Collect individual document info
                for doc in unique_docs:
                    doc_chunks = df[df['metadata'].apply(lambda x: x['source'] == doc)]
                    doc_metadata = doc_chunks.iloc[0]['metadata']
                    stats['documents'].append({
                        'filename': doc_metadata['filename'],
                        'path': doc_metadata['source'],
                        'chunks': len(doc_chunks),
                        'last_modified': doc_metadata.get('last_modified', 'N/A'),
                        'size': doc_metadata.get('file_size', 0)
                    })
                
                # Find last update
                last_modified = max([doc.get('last_modified', '1970-01-01') 
                                   for doc in stats['documents']])
                stats['last_updated'] = last_modified
    
    return stats 