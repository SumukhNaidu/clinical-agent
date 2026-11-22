// Renders the subset of markdown the domain prompts ask for:
// pipe tables, "- " bullet lists, ⚠️ disclaimers and plain paragraphs.

const isTableRow = (line) => line.trim().startsWith('|') && line.trim().endsWith('|');
const isDivider = (line) => /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(line.trim());
const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

function parseBlocks(text) {
  const lines = text.split('\n');
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (isTableRow(line)) {
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) {
        if (!isDivider(lines[i])) rows.push(cells(lines[i]));
        i++;
      }
      blocks.push({ type: 'table', header: rows[0], rows: rows.slice(1) });
    } else if (/^\s*[-*•]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*•]\s+/, ''));
        i++;
      }
      blocks.push({ type: 'list', items });
    } else if (line.trim()) {
      const para = [];
      while (i < lines.length && lines[i].trim() && !isTableRow(lines[i]) && !/^\s*[-*•]\s+/.test(lines[i])) {
        para.push(lines[i]);
        i++;
      }
      const joined = para.join('\n');
      blocks.push({ type: joined.startsWith('⚠️') ? 'disclaimer' : 'para', text: joined });
    } else {
      i++;
    }
  }
  return blocks;
}

export default function MessageContent({ text }) {
  return (
    <div className="message-content">
      {parseBlocks(text || '').map((block, idx) => {
        if (block.type === 'table') {
          return (
            <div key={idx} className="md-table-wrap">
              <table className="md-table">
                {block.header && (
                  <thead><tr>{block.header.map((h, j) => <th key={j}>{h}</th>)}</tr></thead>
                )}
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r}>{row.map((c, j) => <td key={j}>{c}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.type === 'list') {
          return <ul key={idx}>{block.items.map((item, j) => <li key={j}>{item}</li>)}</ul>;
        }
        if (block.type === 'disclaimer') {
          return <p key={idx} className="disclaimer">{block.text}</p>;
        }
        return <p key={idx}>{block.text}</p>;
      })}
    </div>
  );
}
