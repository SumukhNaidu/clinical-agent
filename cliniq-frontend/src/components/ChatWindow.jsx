
import { useState, useRef, useEffect } from 'react';
import './ChatWindow.css';

export default function ChatWindow({ docInfo, messages, onSendMessage, onCitationClick, onNewDoc }) {
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputText.trim() || isSending) return;
    
    const text = inputText.trim();
    setInputText('');
    setIsSending(true);
    
    try {
      await onSendMessage(text);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div className="doc-info">
          <h2>{docInfo.filename}</h2>
          <p className="doc-meta">{docInfo.chunk_count} chunks processed</p>
        </div>
        <button className="new-doc-button" onClick={onNewDoc}>
          New Document
        </button>
      </div>
      
      <div className="chat-messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="message-bubble">
              <p>{msg.content}</p>
              {msg.citations && msg.citations.length > 0 && (
                <div className="citations">
                  {msg.citations.map((cite, citeIdx) => (
                    <button
                      key={citeIdx}
                      className="citation-chip"
                      onClick={() => onCitationClick(cite)}
                    >
                      {cite.page ? `[p. ${cite.page}]` : `[${cite.chunk_id}]`}
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
