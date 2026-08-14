import { useState, useEffect } from 'react';
import './DomainSelector.css';

const DOMAINS = [
  { key: 'general', label: 'General' },
  { key: 'legal', label: 'Legal' },
  { key: 'finance', label: 'Finance' },
  { key: 'research', label: 'Research' }
];

export default function DomainSelector({ domain, onChange }) {
  const [value, setValue] = useState(domain || (import.meta.env.VITE_DOMAIN || 'general'));

  useEffect(() => {
    onChange?.(value);
    try { localStorage.setItem('cliniq_domain', value); } catch (e) {}
  }, [value]);

  useEffect(() => {
    const stored = localStorage.getItem('cliniq_domain');
    if (stored) setValue(stored);
  }, []);

  return (
    <div className="domain-selector">
      <label htmlFor="domain-select">Domain:</label>
      <select id="domain-select" value={value} onChange={(e) => setValue(e.target.value)}>
        {DOMAINS.map(d => (
          <option key={d.key} value={d.key}>{d.label}</option>
        ))}
      </select>
    </div>
  );
}
