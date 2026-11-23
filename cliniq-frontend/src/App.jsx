
import { useEffect, useState } from 'react';
import './App.css';
import './components/Inspector.css';
import UploadZone from './components/UploadZone';
import ChatWindow from './components/ChatWindow';
import CitationDrawer from './components/CitationDrawer';
import DomainSelector from './components/DomainSelector';
import Inspector from './components/Inspector';
import DocumentList from './components/DocumentList';
import { apiClient } from './api/client';

const CURRENT_DOC_KEY = 'cliniq_current_doc';

function loadSavedDoc() {
  try {
    return JSON.parse(localStorage.getItem(CURRENT_DOC_KEY)) || null;
  } catch {
    return null;
  }
}

function saveDoc(doc) {
  try {
    if (doc) localStorage.setItem(CURRENT_DOC_KEY, JSON.stringify(doc));
    else localStorage.removeItem(CURRENT_DOC_KEY);
  } catch {
    // Storage blocked (private window): the app still works, it just won't remember
  }
}

function App() {
  // "#inspector" in the URL opens the RAG Inspector; chat state is kept while switching
  const [showInspector, setShowInspector] = useState(window.location.hash === '#inspector');

  useEffect(() => {
    const onHashChange = () => setShowInspector(window.location.hash === '#inspector');
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // The open document is remembered so closing or reloading the tab brings it back
  const [currentDoc, setCurrentDoc] = useState(loadSavedDoc);
  const [messages, setMessages] = useState([]);
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [error, setError] = useState(null);
  const initialDomain = loadSavedDoc()?.domain || import.meta.env.VITE_DOMAIN || (typeof window !== 'undefined' && localStorage.getItem('cliniq_domain')) || 'general';
  const [domain, setDomain] = useState(initialDomain);
  const [domains, setDomains] = useState([]);
  const [documents, setDocuments] = useState([]);

  const refreshDocuments = () =>
    apiClient.listDocuments().then((docs) => { setDocuments(docs); return docs; });

  useEffect(() => {
    apiClient.getDomains().then(setDomains).catch(() => {});

    refreshDocuments()
      .then((docs) => {
        const saved = loadSavedDoc();
        if (!saved) return;
        if (docs.some((d) => d.doc_id === saved.doc_id)) {
          loadHistory(saved.doc_id);
        } else {
          // The saved document was deleted elsewhere
          saveDoc(null);
          setCurrentDoc(null);
        }
      })
      .catch(() => {
        // Backend unreachable: still try to restore the chat once it answers
        const saved = loadSavedDoc();
        if (saved) loadHistory(saved.doc_id);
      });
  }, []);

  const domainInfo = domains.find((d) => d.key === domain);

  const loadHistory = async (docId) => {
    try {
      const { history } = await apiClient.getSessionHistory(docId);
      setMessages(history.map((m) => ({ role: m.role, content: m.content, citations: m.citations || undefined })));
    } catch (err) {
      setError(`Could not load chat history: ${err.message}`);
    }
  };

  const openDocument = (doc) => {
    const info = { doc_id: doc.doc_id, filename: doc.filename, chunk_count: doc.chunk_count, domain: doc.domain };
    setCurrentDoc(info);
    saveDoc(info);
    if (doc.domain) setDomain(doc.domain);
    setMessages([]);
    setSelectedCitation(null);
    setError(null);
    loadHistory(doc.doc_id);
  };

  const handleDeleteDocument = async (doc) => {
    try {
      await apiClient.deleteDocument(doc.doc_id);
      await refreshDocuments();
    } catch (err) {
      setError(err.message || 'Delete failed');
    }
  };

  const handleUploadSuccess = async (file) => {
    try {
      const result = await apiClient.uploadDocument(file, domain);
      openDocument({ ...result, domain });
      refreshDocuments().catch(() => {});
    } catch (err) {
      setError(err.message || 'Upload failed');
    }
  };

  const handleSendMessage = async (text) => {
    // Add user message to UI immediately
    const userMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    
    try {
      const result = await apiClient.queryDocument(currentDoc.doc_id, text, domain);
      const assistantMessage = {
        role: 'assistant',
        content: result.answer,
        citations: result.citations
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err.message || 'Query failed');
      // Remove user message on error? Or show error message in chat?
      // Let's show an error message in chat
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, there was an error processing your question. Please try again.'
      };
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  const handleNewDoc = () => {
    setCurrentDoc(null);
    saveDoc(null);
    setMessages([]);
    setSelectedCitation(null);
    refreshDocuments().catch(() => {});
  };

  const openInspector = () => { window.location.hash = 'inspector'; };

  if (showInspector) {
    return <Inspector onBack={() => { window.location.hash = ''; }} />;
  }

  return (
    <div className="app">
      {/* In the chat view the button lives in the chat header instead */}
      {!currentDoc && (
        <button className="inspector-link" onClick={openInspector}>
          🔍 Inspector
        </button>
      )}

      {error && (
        <div className="error-toast">
          {error}
          <button className="close-toast" onClick={() => setError(null)}>×</button>
        </div>
      )}
      
      {!currentDoc ? (
        <div className="landing-page">
          <header className="app-header">
            <h1 className="app-title">ClinIQ</h1>
            <p className="app-subtitle">Document Intelligence Platform</p>
            <DomainSelector domain={domain} domains={domains} onChange={setDomain} />
          </header>
          <UploadZone
            onUploadSuccess={handleUploadSuccess}
            onError={setError}
          />
          <DocumentList
            documents={documents}
            domains={domains}
            onOpen={openDocument}
            onDelete={handleDeleteDocument}
          />
        </div>
      ) : (
        <ChatWindow
          docInfo={currentDoc}
          domainInfo={domainInfo}
          messages={messages}
          onSendMessage={handleSendMessage}
          onCitationClick={setSelectedCitation}
          onNewDoc={handleNewDoc}
          onOpenInspector={openInspector}
        />
      )}
      
      {selectedCitation && (
        <CitationDrawer
          citation={selectedCitation}
          onClose={() => setSelectedCitation(null)}
        />
      )}
    </div>
  );
}

export default App;
