
import { useEffect, useMemo, useState } from 'react';
import { inspectorApi } from '../api/client';
import './Inspector.css';

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:3000';
const PROMETHEUS_URL = import.meta.env.VITE_PROMETHEUS_URL || 'http://localhost:9090';

const fmtSeconds = (s) => (s == null ? '–' : s < 1 ? `${Math.round(s * 1000)} ms` : `${s.toFixed(1)} s`);
const fmtNum = (n) => (n == null ? '–' : n.toLocaleString());

// Blue (negative) → neutral → green (positive), scaled to the largest magnitude
function heatColor(value, maxAbs) {
  const t = Math.max(-1, Math.min(1, value / (maxAbs || 1)));
  const alpha = Math.abs(t);
  return t >= 0 ? `rgba(91, 208, 160, ${alpha})` : `rgba(88, 166, 255, ${alpha})`;
}

function Heatmap({ values, columns = 32, cell = 10, title }) {
  const maxAbs = Math.max(...values.map(Math.abs), 1e-6);
  return (
    <div className="heatmap" style={{ gridTemplateColumns: `repeat(${columns}, ${cell}px)` }} title={title}>
      {values.map((v, i) => (
        <span
          key={i}
          style={{ width: cell, height: cell, background: heatColor(v, maxAbs) }}
          title={`dim ${i}: ${v}`}
        />
      ))}
    </div>
  );
}

function TimeBar({ parts }) {
  const total = parts.reduce((sum, p) => sum + (p.value || 0), 0) || 1;
  return (
    <div className="time-bar">
      {parts.filter((p) => p.value > 0).map((p) => (
        <span
          key={p.label}
          className={`seg seg-${p.key}`}
          style={{ width: `${(p.value / total) * 100}%` }}
          title={`${p.label}: ${fmtSeconds(p.value)}`}
        />
      ))}
    </div>
  );
}

// ============================================================
// Overview + recent activity
// ============================================================

function OverviewPanel({ overview }) {
  const { models, splitter, vector_store: store, activity } = overview;
  return (
    <>
      <section className="cards">
        <div className="card">
          <h4>Answer model</h4>
          <p className="mono">{models.llm}</p>
        </div>
        <div className="card">
          <h4>Embedding model</h4>
          <p className="mono">{models.embedding}</p>
          {models.query_prefix && (
            <p className="hint">Question prefix: <code>{models.query_prefix.replace('\n', ' ⏎ ')}</code></p>
          )}
        </div>
        <div className="card">
          <h4>Chunking</h4>
          <p>{splitter.chunk_size} chars max · {splitter.chunk_overlap} overlap</p>
          <p className="hint">Splits on: {splitter.separators.map((s) => JSON.stringify(s)).join(' → ')}</p>
        </div>
        <div className="card">
          <h4>Vector store</h4>
          <p>{store.collections} documents · {fmtNum(store.total_chunks)} vectors</p>
          <p className="hint">Chroma {store.type === 'Client' ? 'server (HTTP)' : 'embedded'} · HNSW index</p>
        </div>
      </section>

      <section className="panel">
        <h3>Recent questions <span className="muted">(since backend start)</span></h3>
        {activity.queries.length === 0 ? (
          <p className="muted">Ask a question in the app or run a search below to see token usage here.</p>
        ) : (
          <>
            <div className="legend">
              <span><i className="seg-load" /> model load</span>
              <span><i className="seg-embed" /> embed question</span>
              <span><i className="seg-search" /> vector search</span>
              <span><i className="seg-prompt" /> read prompt</span>
              <span><i className="seg-gen" /> generate answer</span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Question</th><th>Tokens in</th><th>Tokens out</th><th>Speed</th><th>Total</th><th>Where the time went</th>
                </tr>
              </thead>
              <tbody>
                {activity.queries.map((q, i) => (
                  <tr key={i}>
                    <td className="q" title={q.answer_preview}>{q.question}</td>
                    <td>{fmtNum(q.llm?.prompt_tokens)}</td>
                    <td>{fmtNum(q.llm?.completion_tokens)}</td>
                    <td>{q.llm?.tokens_per_second ? `${q.llm.tokens_per_second} tok/s` : '–'}</td>
                    <td>{fmtSeconds(q.total_seconds)}</td>
                    <td>
                      <TimeBar parts={[
                        { key: 'load', label: 'Model load', value: q.llm?.load_seconds },
                        { key: 'embed', label: 'Embed question', value: q.retrieval?.embed_seconds },
                        { key: 'search', label: 'Vector search', value: q.retrieval?.search_seconds },
                        { key: 'prompt', label: 'Read prompt', value: q.llm?.prompt_eval_seconds },
                        { key: 'gen', label: 'Generate', value: q.llm?.generation_seconds },
                      ]} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {activity.uploads.length > 0 && (
        <section className="panel">
          <h3>Recent uploads</h3>
          <table className="table">
            <thead>
              <tr><th>File</th><th>Pages</th><th>Characters</th><th>Chunks</th><th>Embed tokens</th><th>Load / split / embed / store</th></tr>
            </thead>
            <tbody>
              {activity.uploads.map((u) => (
                <tr key={u.doc_id}>
                  <td className="q">{u.filename}</td>
                  <td>{u.pages}</td>
                  <td>{fmtNum(u.characters)}</td>
                  <td>{u.chunks}</td>
                  <td>{fmtNum(u.embed_tokens)}</td>
                  <td>
                    {Object.values(u.stages_seconds).map(fmtSeconds).join(' / ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}

// ============================================================
// Chunks tab
// ============================================================

function ChunksTab({ docId }) {
  const [data, setData] = useState(null);
  const [fullVector, setFullVector] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    inspectorApi.chunks(docId).then(setData).catch((e) => setError(e.message));
  }, [docId]);

  const showFull = async (index) => {
    const res = await inspectorApi.chunkEmbedding(docId, index);
    setFullVector((prev) => ({ ...prev, [index]: res.embedding }));
  };

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading chunks…</p>;

  return (
    <div>
      <p className="explain">
        The document's text was split into <b>{data.chunks.length}</b> chunks. Each chunk is stored in Chroma
        collection <code>{data.collection.name}</code> together with its embedding: a list
        of {data.chunks[0]?.embedding.dimensions} numbers. <span className="overlap-sample">Highlighted text</span> is
        repeated from the end of the previous chunk (the overlap), so sentences cut at a boundary are never lost.
      </p>
      {data.chunks.map((c) => (
        <article key={c.id} className="chunk">
          <header>
            <b>Chunk {c.index}</b>
            <span>page {c.page ?? '–'}</span>
            <span>{c.characters} chars · {c.words} words</span>
            {c.overlap_with_previous > 0 && <span>{c.overlap_with_previous} chars overlap</span>}
            <span className="mono">‖v‖ = {c.embedding.norm}</span>
          </header>
          <p className="chunk-text">
            {c.overlap_with_previous > 0 && <mark>{c.text.slice(0, c.overlap_with_previous)}</mark>}
            {c.text.slice(c.overlap_with_previous)}
          </p>
          <div className="vector-row">
            <div>
              <span className="hint">
                {fullVector[c.index] ? `All ${c.embedding.dimensions} dimensions` : `First ${c.embedding.preview.length} of ${c.embedding.dimensions} dimensions`}
              </span>
              <Heatmap values={fullVector[c.index] || c.embedding.preview} columns={fullVector[c.index] ? 64 : 32} cell={fullVector[c.index] ? 7 : 10} />
            </div>
            {!fullVector[c.index] && (
              <button className="link-button" onClick={() => showFull(c.index)}>Show full vector</button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

// ============================================================
// Embedding map tab (PCA)
// ============================================================

function MapTab({ docId }) {
  const [data, setData] = useState(null);
  const [question, setQuestion] = useState('');
  const [hover, setHover] = useState(null);
  const [selected, setSelected] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = (q) => {
    setLoading(true);
    inspectorApi.projection(docId, q).then(setData).finally(() => setLoading(false));
  };

  useEffect(() => {
    setData(null);
    setSelected(null);
    setChunks([]);
    load();
    // Chunk text for the panel shown when a dot is clicked
    inspectorApi.chunks(docId).then((res) => setChunks(res.chunks)).catch(() => {});
  }, [docId]);

  const selectedChunk = chunks.find((c) => c.index === selected);

  const { points = [], query } = data || {};
  const bounds = useMemo(() => {
    const all = [...points, ...(query ? [query] : [])];
    const xs = all.map((p) => p.x), ys = all.map((p) => p.y);
    const pad = 0.05;
    return {
      minX: Math.min(...xs, 0) - pad, maxX: Math.max(...xs, 0) + pad,
      minY: Math.min(...ys, 0) - pad, maxY: Math.max(...ys, 0) + pad,
    };
  }, [points, query]);

  const W = 640, H = 420;
  const sx = (x) => ((x - bounds.minX) / (bounds.maxX - bounds.minX || 1)) * (W - 40) + 20;
  const sy = (y) => H - (((y - bounds.minY) / (bounds.maxY - bounds.minY || 1)) * (H - 40) + 20);
  const pages = [...new Set(points.map((p) => p.page))];
  const pageColor = (page) => `hsl(${(pages.indexOf(page) * 360) / Math.max(pages.length, 1)}, 65%, 62%)`;

  return (
    <div>
      <p className="explain">
        Each dot is one chunk. Its 1024-number embedding is squashed into 2 dimensions (PCA) so you can see it:
        chunks about similar topics land close together. Type a question to see where it lands — the nearest dots
        are what the search returns. The 2D view keeps
        about {data ? Math.round((data.explained_variance[0] + data.explained_variance[1]) * 100) : '…'}% of
        the variation, so treat distances here as approximate.
      </p>
      <form className="row" onSubmit={(e) => { e.preventDefault(); load(question.trim() || undefined); }}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Optional: place a question on the map" />
        <button type="submit" disabled={loading}>{loading ? 'Embedding…' : 'Show'}</button>
      </form>
      {points.length < 3 && data && <p className="muted">This document has too few chunks for a meaningful map.</p>}
      <svg viewBox={`0 0 ${W} ${H}`} className="map">
        {points.map((p) => (
          <circle
            key={p.index}
            cx={sx(p.x)} cy={sy(p.y)} r={hover === p.index || selected === p.index ? 8 : 6}
            fill={pageColor(p.page)}
            className={selected === p.index ? 'selected-dot' : ''}
            onMouseEnter={() => setHover(p.index)}
            onMouseLeave={() => setHover(null)}
            onClick={() => setSelected(p.index)}
          >
            <title>Chunk {p.index} · page {p.page ?? '–'} (click to read)</title>
          </circle>
        ))}
        {points.map((p) => (
          <text
            key={`t${p.index}`}
            x={sx(p.x) + 8} y={sy(p.y) + 4}
            className={`map-label clickable ${selected === p.index ? 'selected-label' : ''}`}
            onClick={() => setSelected(p.index)}
          >
            {p.index}
          </text>
        ))}
        {query && (
          <g>
            <circle cx={sx(query.x)} cy={sy(query.y)} r={10} className="query-dot" />
            <text x={sx(query.x) + 13} y={sy(query.y) + 4} className="map-label query-label">your question</text>
          </g>
        )}
      </svg>
      <p className="hint">Colours = page number. Click a dot or its number to read that chunk.</p>

      {selected != null && (
        <article className="chunk map-selection">
          <header>
            <b>Chunk {selected}</b>
            {selectedChunk && (
              <>
                <span>page {selectedChunk.page ?? '–'}</span>
                <span>{selectedChunk.characters} chars · {selectedChunk.words} words</span>
              </>
            )}
            <button className="link-button close" onClick={() => setSelected(null)}>Close ×</button>
          </header>
          <p className="chunk-text">{selectedChunk ? selectedChunk.text : 'Loading text…'}</p>
        </article>
      )}
    </div>
  );
}

// ============================================================
// Search trace tab
// ============================================================

function SearchTab({ docId }) {
  const [question, setQuestion] = useState('');
  const [k, setK] = useState(3);
  const [trace, setTrace] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { setTrace(null); }, [docId]);

  const run = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setTrace(await inspectorApi.search(docId, question.trim(), k));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const maxDistance = trace ? Math.max(...trace.chunks.map((c) => c.distance)) : 1;

  return (
    <div>
      <form className="row" onSubmit={run}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask something about this document" />
        <label className="k-input">top k <input type="number" min="1" max="20" value={k} onChange={(e) => setK(Number(e.target.value))} /></label>
        <button type="submit" disabled={loading}>{loading ? 'Searching…' : 'Trace search'}</button>
      </form>
      <p className="hint">This runs the retrieval step only (no answer is generated), so it is quick.</p>
      {error && <p className="error">{error}</p>}

      {trace && (
        <ol className="steps">
          <li>
            <h4>1 · Embed the question <span className="muted">{fmtSeconds(trace.timings.embed_seconds)} · {trace.timings.embed_tokens} tokens</span></h4>
            <p>The embedding model reads this text (the prefix tells Qwen3-Embedding it is a search query):</p>
            <pre className="mono">{trace.embedded_text}</pre>
            <p>…and returns a vector of {trace.query_embedding.dimensions} numbers (length {trace.query_embedding.norm}, i.e. normalised). First 64:</p>
            <Heatmap values={trace.query_embedding.preview} />
          </li>
          <li>
            <h4>2 · Find the nearest chunks in Chroma <span className="muted">{fmtSeconds(trace.timings.hnsw_search_seconds)}</span></h4>
            <p>
              Chroma's <b>HNSW</b> index links every vector to its closest neighbours. The search starts at an entry
              point and keeps hopping to whichever neighbour is closer to the question, so it doesn't compare against
              every chunk. It measures <b>{trace.distance_metric === 'l2' ? 'squared Euclidean (L2) distance' : trace.distance_metric}</b> —
              smaller means more similar. Because all vectors have length 1, this is equivalent to cosine
              similarity: <code>distance = 2 − 2 × cosine</code>.
            </p>
            <p>Chroma returned the top {trace.k} of {trace.total_chunks} chunks with distances <code>{trace.chroma_distances.join(', ')}</code>.</p>
          </li>
          <li>
            <h4>3 · Every chunk, ranked <span className="muted">(computed here for illustration)</span></h4>
            <p>Highlighted rows are the ones sent to the answer model as context.</p>
            <table className="table ranking">
              <thead>
                <tr><th>#</th><th>Chunk</th><th>Page</th><th>Distance</th><th>Cosine</th><th>Text</th></tr>
              </thead>
              <tbody>
                {trace.chunks.map((c) => (
                  <tr key={c.index} className={c.selected ? 'selected' : ''}>
                    <td>{c.rank}</td>
                    <td>{c.index}</td>
                    <td>{c.page ?? '–'}</td>
                    <td>
                      <div className="dist">
                        <span style={{ width: `${(c.distance / maxDistance) * 100}%` }} />
                        <em>{c.distance}</em>
                      </div>
                    </td>
                    <td>{c.cosine_similarity}</td>
                    <td className="q" title={c.text}>{c.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </li>
        </ol>
      )}
    </div>
  );
}

// ============================================================
// Page
// ============================================================

export default function Inspector({ onBack }) {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);
  const [docId, setDocId] = useState(null);
  const [tab, setTab] = useState('chunks');

  const refresh = () => {
    inspectorApi.overview()
      .then((o) => {
        setOverview(o);
        setError(null);
        setDocId((current) => current || o.documents[0]?.doc_id || null);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="inspector">
      <header className="inspector-header">
        <div>
          <h1>RAG Inspector</h1>
          <p className="muted">How your documents become chunks and vectors, and how questions find them.</p>
        </div>
        <nav>
          <a href={GRAFANA_URL} target="_blank" rel="noreferrer">Grafana ↗</a>
          <a href={PROMETHEUS_URL} target="_blank" rel="noreferrer">Prometheus ↗</a>
          <a href={`${inspectorApi.baseUrl}/metrics`} target="_blank" rel="noreferrer">/metrics ↗</a>
          <button onClick={onBack}>← Back to app</button>
        </nav>
      </header>

      {error && <p className="error">Could not reach the backend: {error}</p>}
      {!overview && !error && <p className="muted">Loading…</p>}

      {overview && (
        <>
          <OverviewPanel overview={overview} />

          <section className="panel">
            <h3>Documents in Chroma</h3>
            {overview.documents.length === 0 ? (
              <p className="muted">No documents yet — upload one in the app.</p>
            ) : (
              <>
                <div className="row">
                  <select value={docId || ''} onChange={(e) => setDocId(e.target.value)}>
                    {overview.documents.map((d) => (
                      <option key={d.doc_id} value={d.doc_id}>
                        {d.filename} — {d.chunks} chunks
                      </option>
                    ))}
                  </select>
                  <div className="tabs">
                    {[['chunks', 'Chunks & embeddings'], ['map', 'Embedding map'], ['search', 'Search trace']].map(([key, label]) => (
                      <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>
                    ))}
                  </div>
                </div>
                {docId && tab === 'chunks' && <ChunksTab docId={docId} />}
                {docId && tab === 'map' && <MapTab docId={docId} />}
                {docId && tab === 'search' && <SearchTab docId={docId} />}
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
