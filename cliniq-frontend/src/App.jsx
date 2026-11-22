
import { useEffect, useState } from 'react';
import './App.css';
import './components/Inspector.css';
import UploadZone from './components/UploadZone';
import ChatWindow from './components/ChatWindow';
import CitationDrawer from './components/CitationDrawer';
import DomainSelector from './components/DomainSelector';
import Inspector from './components/Inspector';
import { apiClient } from './api/client';

function App() {
  // "#inspector" in the URL opens the RAG Inspector; chat state is kept while switching
  const [showInspector, setShowInspector] = useState(window.location.hash === '#inspector');

  useEffect(() => {
    const onHashChange = () => setShowInspector(window.location.hash === '#inspector');
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const [currentDoc, setCurrentDoc] = useState(null);
  const [messages, setMessages] = useState([]);
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [error, setError] = useState(null);
  const initialDomain = import.meta.env.VITE_DOMAIN || (typeof window !== 'undefined' && localStorage.getItem('cliniq_domain')) || 'general';
  const [domain, setDomain] = useState(initialDomain);
  const [domains, setDomains] = useState([]);

  useEffect(() => {
    apiClient.getDomains().then(setDomains).catch(() => {});
  }, []);

  const domainInfo = domains.find((d) => d.key === domain);

  const handleUploadSuccess = async (file) => {
    try {
      const result = await apiClient.uploadDocument(file, domain);
      setCurrentDoc(result);
      setMessages([]);
      setError(null);
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
    setMessages([]);
    setSelectedCitation(null);
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
