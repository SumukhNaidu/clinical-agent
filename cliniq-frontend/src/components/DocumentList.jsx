import { useState } from 'react';
import './DocumentList.css';

const formatDate = (iso) => {
  if (!iso) return 'earlier upload';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

export default function DocumentList({ documents, domains, onOpen, onDelete }) {
  const [deleting, setDeleting] = useState(null);

  if (!documents?.length) return null;

  const domainLabel = (key) => domains.find((d) => d.key === key)?.label || key;

  const handleDelete = async (doc) => {
    if (!window.confirm(`Delete "${doc.filename}"? Its chunks, embeddings and chat history will be removed.`)) return;
    setDeleting(doc.doc_id);
    try {
      await onDelete(doc);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <section className="document-list">
      <h3>Your documents</h3>
      <ul>
        {documents.map((doc) => (
          <li key={doc.doc_id}>
            <button className="document-open" onClick={() => onOpen(doc)} disabled={deleting === doc.doc_id}>
              <span className="document-name">{doc.filename}</span>
              <span className="document-meta">
                <span className="document-domain">{domainLabel(doc.domain)}</span>
                {doc.chunk_count} chunks
                {doc.questions > 0 && ` · ${doc.questions} question${doc.questions === 1 ? '' : 's'}`}
                {` · ${formatDate(doc.uploaded_at)}`}
              </span>
            </button>
            <button
              className="document-delete"
              title="Delete document"
              onClick={() => handleDelete(doc)}
              disabled={deleting === doc.doc_id}
            >
              {deleting === doc.doc_id ? '…' : 'Delete'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
