
import { useState, useRef, useEffect } from 'react';
import './ChatWindow.css';
import MessageContent from './MessageContent';

export default function ChatWindow({ docInfo, domainInfo, messages, onSendMessage, onCitationClick, onNewDoc, onOpenInspector }) {
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const send = async (text) => {
    if (!text || isSending) return;
    setIsSending(true);
    try {
      await onSendMessage(text);
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const text = inputText.trim();
    if (!text || isSending) return;
    setInputText('');
    await send(text);
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div className="doc-info">
          <h2>{docInfo.filename}</h2>
          <p className="doc-meta">
            {docInfo.chunk_count} chunks processed{domainInfo ? ` · ${domainInfo.label} domain` : ''}
          </p>
        </div>
        <div className="header-actions">
          {onOpenInspector && (
            <button className="inspector-header-button" onClick={onOpenInspector}>
              🔍 Inspector
            </button>
          )}
          <button className="new-doc-button" onClick={onNewDoc}>
            New Document
          </button>
        </div>
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 && domainInfo?.suggested_questions?.length > 0 && (
          <div className="suggestions">
            <p className="suggestions-title">Try asking ({domainInfo.label}):</p>
            <div className="suggestion-list">
              {domainInfo.suggested_questions.map((q) => (
                <button key={q} className="suggestion-chip" disabled={isSending} onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="message-bubble">
              {msg.role === 'assistant' ? <MessageContent text={msg.content} /> : <p>{msg.content}</p>}
              {msg.citations && msg.citations.length > 0 && (
                <div className="citations">
                  {msg.citations.map((cite, citeIdx) => (
                    <button
                      key={citeIdx}
                      className="citation-chip"
                      onClick={() => onCitationClick(cite)}
                    >
                      {/* Matches the [Chunk N] references in the answer; pages are 1-based */}
                      [{cite.label || `Chunk ${citeIdx + 1}`}{Number.isInteger(cite.page) ? ` · p. ${cite.page + 1}` : ''}]
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {isSending && (
          <div className="message assistant">
            <div className="message-bubble typing">
              <span>...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <form className="chat-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          placeholder="Ask a question about your document..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          disabled={isSending}
        />
        <button
          type="submit"
          className="send-button"
          disabled={!inputText.trim() || isSending}
        >
          Send
        </button>
      </form>
    </div>
  );
}
