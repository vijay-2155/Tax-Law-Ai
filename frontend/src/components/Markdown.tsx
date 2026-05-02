import { useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Copy, Check } from "lucide-react";

// Convert §NNN patterns (LLM output) in non-code, non-heading text to markdown links
function preprocessSectionRefs(text: string): string {
  const parts = text.split(/(```[\s\S]*?```|`[^`\n]+`)/g);
  return parts.map((part, i) => {
    if (i % 2 === 0) {
      return part.split("\n").map(line =>
        /^#{1,6}\s/.test(line)
          ? line
          : line.replace(/[§#](\d+[A-Za-z]*)/g, "[#$1](section-ref:$1)")
      ).join("\n");
    }
    return part;
  }).join("");
}

function SectionRef({ section, act }: { section: string; act?: string }) {
  const pillStyle: CSSProperties = { margin: "0 2px", verticalAlign: "middle", textDecoration: "none" };
  if (act) {
    return (
      <Link to={`/section/${act}/${section}`} className="section-pill" style={pillStyle}>
        #{section}
      </Link>
    );
  }
  return <span className="section-pill" style={pillStyle}>#{section}</span>;
}

function TableRenderer({ children }: any) {
  const tableRef = useRef<HTMLTableElement>(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (tableRef.current) {
      const text = Array.from(tableRef.current.rows).map(row =>
        Array.from(row.cells).map(cell =>
          cell.innerText.replace(/\r?\n|\r/g, " ").trim()
        ).join("\t")
      ).join("\n");
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="relative group my-5">
      <button
        onClick={handleCopy}
        title="Copy Table"
        className="absolute right-2 top-2 z-10 opacity-0 group-hover:opacity-100 transition-all rounded p-1.5 shadow-sm flex items-center justify-center"
        style={{
          background: "var(--bg-hover)",
          border: "1px solid var(--border-default)",
        }}
      >
        {copied
          ? <Check className="w-3.5 h-3.5" style={{ color: "var(--green)" }} />
          : <Copy className="w-3.5 h-3.5" style={{ color: "var(--text-muted)" }} />}
      </button>
      <div className="overflow-x-auto rounded-xl shadow-sm" style={{ border: "1px solid var(--border-subtle)" }}>
        <table ref={tableRef} className="w-full text-sm border-collapse">{children}</table>
      </div>
    </div>
  );
}

function stripThinkTags(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
}

export default function Markdown({ children, act }: { children: string; act?: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={{
        // ── Headings ─────────────────────────────────────────────────────────
        h1: ({ children }) => (
          <h1
            className="text-xl font-bold mt-5 mb-2"
            style={{ color: "var(--text-primary)", fontFamily: "'Noto Serif', serif" }}
          >
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2
            className="text-lg font-bold mt-4 mb-2 pb-1"
            style={{
              color: "var(--text-primary)",
              fontFamily: "'Noto Serif', serif",
              borderBottom: "1px solid var(--border-faint)",
            }}
          >
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3
            className="text-base font-semibold mt-3 mb-1.5"
            style={{ color: "var(--text-primary)" }}
          >
            {children}
          </h3>
        ),
        h4: ({ children }) => (
          <h4
            className="text-sm font-semibold mt-3 mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            {children}
          </h4>
        ),

        // ── Paragraphs & text ─────────────────────────────────────────────────
        p: ({ children }) => (
          <p
            className="text-sm leading-relaxed mb-3"
            style={{ color: "var(--text-primary)" }}
          >
            {children}
          </p>
        ),
        strong: ({ children }) => (
          <strong
            className="font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {children}
          </strong>
        ),
        em: ({ children }) => (
          <em style={{ color: "var(--text-secondary)" }}>{children}</em>
        ),

        // ── Blockquote ────────────────────────────────────────────────────────
        blockquote: ({ children }) => (
          <blockquote
            className="pl-4 my-3 italic text-sm"
            style={{
              borderLeft: "3px solid var(--accent)",
              color: "var(--text-secondary)",
              background: "var(--accent-dim)",
              borderRadius: "0 6px 6px 0",
              padding: "8px 12px",
            }}
          >
            {children}
          </blockquote>
        ),

        // ── Code ──────────────────────────────────────────────────────────────
        code: ({ children, className }) => {
          const isBlock = className?.startsWith("language-");
          if (!isBlock) {
            const text = String(children).trim();
            const match = text.match(/^[#§](\d+[A-Za-z]*)$/);
            if (match) return <SectionRef section={match[1]} act={act} />;
          }
          return isBlock ? (
            <code
              className="block rounded-lg p-3 text-xs font-mono overflow-x-auto my-3 whitespace-pre"
              style={{
                background: "var(--bg-hover)",
                border: "1px solid var(--border-subtle)",
                color: "var(--accent)",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {children}
            </code>
          ) : (
            <code
              className="rounded px-1.5 py-0.5 text-xs font-mono"
              style={{
                background: "var(--bg-hover)",
                border: "1px solid var(--border-default)",
                color: "var(--accent)",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {children}
            </code>
          );
        },
        pre: ({ children }) => <>{children}</>,

        // ── Lists ─────────────────────────────────────────────────────────────
        ul: ({ children }) => (
          <ul
            className="list-disc pl-5 mb-3 space-y-1 text-sm"
            style={{ color: "var(--text-primary)" }}
          >
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol
            className="list-decimal pl-5 mb-3 space-y-1 text-sm"
            style={{ color: "var(--text-primary)" }}
          >
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed" style={{ color: "var(--text-primary)" }}>
            {children}
          </li>
        ),

        // ── Horizontal rule ───────────────────────────────────────────────────
        hr: () => <hr className="my-5" style={{ borderColor: "var(--border-subtle)" }} />,

        // ── Tables ────────────────────────────────────────────────────────────
        table: TableRenderer,
        thead: ({ children }) => (
          <thead style={{ background: "var(--bg-hover)" }}>{children}</thead>
        ),
        tbody: ({ children }) => (
          <tbody style={{ background: "var(--bg-surface)" }}>{children}</tbody>
        ),
        tr: ({ children }) => (
          <tr
            className="transition-colors"
            style={{ borderBottom: "1px solid var(--border-faint)" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-panel)")}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            {children}
          </tr>
        ),
        th: ({ children }) => (
          <th
            className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
            style={{
              color: "var(--text-secondary)",
              borderBottom: "1px solid var(--border-subtle)",
            }}
          >
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td
            className="px-4 py-2.5 text-sm align-top leading-relaxed"
            style={{
              color: "var(--text-primary)",
              borderBottom: "1px solid var(--border-faint)",
            }}
          >
            {children}
          </td>
        ),

        // ── Links — section-ref: → internal pill, else external ───────────────
        a: ({ href, children }) => {
          if (href?.startsWith("section-ref:")) {
            const section = href.replace("section-ref:", "");
            return <SectionRef section={section} act={act} />;
          }
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 transition-colors"
              style={{ color: "var(--blue-mid)" }}
              onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
              onMouseLeave={e => (e.currentTarget.style.color = "var(--blue-mid)")}
            >
              {children}
            </a>
          );
        },
      }}
    >
      {preprocessSectionRefs(stripThinkTags(children))}
    </ReactMarkdown>
  );
}
