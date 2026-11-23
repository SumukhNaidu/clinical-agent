import './DomainSelector.css';

// Shown until the backend's /domains list loads (or if it can't be reached)
export const FALLBACK_DOMAINS = [
  { key: 'general', label: 'General' },
  { key: 'legal', label: 'Legal' },
  { key: 'finance', label: 'Finance' },
  { key: 'research', label: 'Research' },
  { key: 'medical', label: 'Medical' }
];

export default function DomainSelector({ domain, domains, onChange }) {
  const options = domains?.length ? domains : FALLBACK_DOMAINS;
  const current = options.find((d) => d.key === domain);

  const handleChange = (value) => {
    onChange?.(value);
    try { localStorage.setItem('cliniq_domain', value); } catch (e) {}
  };

  return (
    <div className="domain-selector">
      <label htmlFor="domain-select">Domain:</label>
      <select id="domain-select" value={domain} onChange={(e) => handleChange(e.target.value)}>
        {options.map((d) => (
          <option key={d.key} value={d.key}>{d.label}</option>
        ))}
      </select>
      {current?.description && <p className="domain-description">{current.description}</p>}
    </div>
  );
}
