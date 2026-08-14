
import './CitationDrawer.css';

export default function CitationDrawer({ citation, onClose }) {
  if (!citation) return null;
  
  return (
    <div className="citation-drawer-overlay" onClick={onClose}>
      <div className="citation-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h3>Source Citation</h3>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        <div className="drawer-content">
          <div className="citation-meta">
          {citation.page && <span className="meta-item">Page: {citation.page}</span>}
          <span className="meta-item">Chunk: {citation.chunk_id}</span>
        </div>
        <div className="citation-text">
          {citation.content}
        </div>
        </div>
      </div>
    </div>
  );
}
