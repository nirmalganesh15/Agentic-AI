export interface Source {
  id: string;
  citation: string | null; // null = cited by the model but not retrieved in this request
}

const CITATION_ID = /[A-Z]{2,}-[A-Z]{2,}-\d{3} p\.\d+/g;
const CITATION_GROUP = /\[([A-Z]{2,}-[A-Z]{2,}-\d{3} p\.\d+(?:\s*[,;]\s*[A-Z]{2,}-[A-Z]{2,}-\d{3} p\.\d+)*)\]/g;
const SKU = /\b[A-Z]{3}-\d{4}\b/g;

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, c => ESCAPES[c]);
}

export function eur(value: number | null | undefined): string {
  if (value == null) return '–';
  return '€' + value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Sources cited in the answer, in order of first appearance. */
export function citedSources(answer: string, known: Map<string, string>): Source[] {
  const ids = new Set<string>();
  for (const [, group] of answer.matchAll(CITATION_GROUP)) {
    for (const id of group.match(CITATION_ID) ?? []) ids.add(id);
  }
  return [...ids].map(id => ({ id, citation: known.get(id) ?? null }));
}

function citationChip(id: string, known: Map<string, string>): string {
  const citation = known.get(id);
  return citation
    ? `<span class="cite" title="${escapeHtml(citation)}">${id}</span>`
    : `<span class="cite unverified" title="Not found in the retrieved sources">${id}</span>`;
}

// Input is already HTML-escaped, so only our own tags end up in the output.
function renderInline(text: string, known: Map<string, string>): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(CITATION_GROUP, (_, group: string) =>
      (group.match(CITATION_ID) ?? []).map(id => citationChip(id, known)).join(' '))
    .replace(SKU, sku => `<span class="sku">${sku}</span>`);
}

/** Minimal, safe markdown: paragraphs, bold, inline code, headings, lists, citation and SKU chips. */
export function renderAnswer(answer: string, known: Map<string, string>): string {
  const html: string[] = [];
  let paragraph: string[] = [];
  let list: 'ul' | 'ol' | null = null;

  const flushParagraph = () => {
    if (paragraph.length) html.push(`<p>${paragraph.join('<br>')}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (list) html.push(`</${list}>`);
    list = null;
  };

  for (const rawLine of escapeHtml(answer).split(/\r?\n/)) {
    const line = rawLine.trim();
    const bullet = line.match(/^[-*]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    const heading = line.match(/^#{1,6}\s+(.*)$/);

    if (bullet || numbered) {
      flushParagraph();
      const type = bullet ? 'ul' : 'ol';
      if (list !== type) {
        closeList();
        html.push(`<${type}>`);
        list = type;
      }
      html.push(`<li>${renderInline((bullet ?? numbered)![1], known)}</li>`);
      continue;
    }

    closeList();
    if (!line) {
      flushParagraph();
    } else if (heading) {
      flushParagraph();
      html.push(`<h4>${renderInline(heading[1], known)}</h4>`);
    } else {
      paragraph.push(renderInline(line, known));
    }
  }
  flushParagraph();
  closeList();
  return html.join('');
}
