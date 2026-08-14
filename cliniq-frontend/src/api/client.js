
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8005';

// Default domain can be provided via Vite env `VITE_DOMAIN`
const DEFAULT_DOMAIN = import.meta.env.VITE_DOMAIN || 'general';

export const apiClient = {
  async uploadDocument(file, domain = DEFAULT_DOMAIN) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('domain', domain);
    
    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(error);
    }
    
    return response.json();
  },
  
  async queryDocument(docId, question, domain = DEFAULT_DOMAIN) {
    const response = await fetch(`${API_BASE_URL}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ doc_id: docId, question, domain })
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(error);
    }
    
    return response.json();
  },
  
  async getSessionHistory(docId) {
    const response = await fetch(`${API_BASE_URL}/sessions/${docId}`);
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(error);
    }
    
    return response.json();
  },
  
  async deleteDocument(docId) {
    const response = await fetch(`${API_BASE_URL}/document/${docId}`, {
      method: 'DELETE'
    });
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(error);
    }
    
    return response.json();
  }

  ,
  async streamQueryDocument(docId, question, domain = DEFAULT_DOMAIN, onMessage = () => {}, onDone = () => {}, onError = (e) => {}) {
    try {
      const resp = await fetch(`${API_BASE_URL}/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, question, domain })
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(err);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      let done = false;
      while (!done) {
        const { value, done: rDone } = await reader.read();
        if (value) {
          const chunk = decoder.decode(value);
          // The backend sends a final marker __DONE__ when complete
          if (chunk === '__DONE__') {
            onDone();
            break;
          }
          onMessage(chunk);
        }
        done = rDone;
      }
      onDone();
    } catch (e) {
      onError(e);
    }
  }
};
