
import { useState } from 'react';
import './UploadZone.css';

export default function UploadZone({ onUploadSuccess, onError }) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (file) => {
    if (!file.name.toLowerCase().endsWith('.pdf') && !file.name.toLowerCase().endsWith('.docx')) {
      onError?.('Please upload a PDF or DOCX file');
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      onError?.('File size must be less than 25 MB');
      return;
    }
    setSelectedFile(file);
  };

  const handleFileInputChange = (e) => {
    if (e.target.files.length > 0) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    try {
      const result = await onUploadSuccess(selectedFile);
    } catch (err) {
      onError?.(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="upload-zone-container">
      <div
        className={`upload-zone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="upload-icon">📄</div>
        <h3>Upload your document</h3>
        <p className="upload-subtitle">PDF or DOCX • Max 25 MB</p>
        
        {selectedFile ? (
          <div className="selected-file">
            <span className="file-name">{selectedFile.name}</span>
            <span className="file-size">({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)</span>
          </div>
        ) : (
          <div>
            <input
              type="file"
              id="file-input"
              accept=".pdf,.docx"
              onChange={handleFileInputChange}
              style={{ display: 'none' }}
            />
            <button
              className="browse-button"
              onClick={() => document.getElementById('file-input').click()}
            >
              Browse Files
            </button>
          </div>
        )}
      </div>
      
      {selectedFile && (
        <button
          className="upload-button"
          onClick={handleUpload}
          disabled={isUploading}
        >
          {isUploading ? 'Processing...' : 'Upload & Process'}
        </button>
      )}
    </div>
  );
}
