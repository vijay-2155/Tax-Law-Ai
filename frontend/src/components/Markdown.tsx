import { useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Copy, Check } from "lucide-react";

// Convert §NNN patterns (LLM output) in non-code, non-heading text to markdown links
function preprocessSectionRefs(text: string): string {
  // Split on code spans and fenced code blocks; only transform the non-code parts
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
        Array.from(row.cells).map(cell => {
           // Basic string cleanup for TSV formatting
           return cell.innerText.replace(/\r?\n|\r/g, " ").trim();
        }).join("\t")
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
        className="absolute right-2 top-2 z-10 opacity-0 group-hover:opacity-100 transition-all bg-[#1e1e1e] hover:bg-[#2a2a2a] border border-[#3a3a3a] rounded p-1.5 shadow-md flex items-center justify-center"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-[#a78bfa]" />}
      </button>
      <div className="overflow-x-auto rounded-xl border border-[#2a2a2a] shadow-sm">
        <table ref={tableRef} className="w-full text-base border-collapse">{children}</table>
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
        // Headings
        h1: ({ children }) => <h1 className="text-xl font-bold text-[#ececec] mt-5 mb-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-lg font-bold text-[#ececec] mt-4 mb-2 border-b border-[#2a2a2a] pb-1">{children}</h2>,
        h3: ({ children }) => <h3 className="text-base font-semibold text-[#d4d4d4] mt-3 mb-1.5">{children}</h3>,
        h4: ({ children }) => <h4 className="text-sm font-semibold text-[#c4c4c4] mt-3 mb-1">{children}</h4>,

        // Paragraphs & text
        p: ({ children }) => <p className="text-[#d4d4d4] text-base leading-relaxed mb-3">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-[#ececec]">{children}</strong>,
        em: ({ children }) => <em className="italic text-[#c4c4c4]">{children}</em>,

        // Blockquote
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-[#a78bfa] pl-4 my-3 text-[#8e8ea0] italic">{children}</blockquote>
        ),

        // Code
        code: ({ children, className }) => {
          const isBlock = className?.startsWith("language-");
          if (!isBlock) {
            const text = String(children).trim();
            const match = text.match(/^[#§](\d+[A-Za-z]*)$/);
            if (match) return <SectionRef section={match[1]} act={act} />;
          }
          return isBlock ? (
            <code className="block bg-[#161616] border border-[#2a2a2a] rounded-lg p-3 text-xs font-mono text-[#a78bfa] overflow-x-auto my-3 whitespace-pre">
              {children}
            </code>
          ) : (
            <code className="bg-[#2a2a2a] border border-[#3a3a3a] rounded px-1.5 py-0.5 text-xs font-mono text-[#a78bfa]">
              {children}
            </code>
          );
        },
        pre: ({ children }) => <>{children}</>,

        // Lists
        ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1 text-base text-[#d4d4d4]">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1 text-base text-[#d4d4d4]">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,

        // Horizontal rule
        hr: () => <hr className="border-[#2a2a2a] my-5" />,

        // Tables — requires remark-gfm
        table: TableRenderer,
        thead: ({ children }) => (
          <thead className="bg-[#1e1e1e] sticky top-0">{children}</thead>
        ),
        tbody: ({ children }) => (
          <tbody className="divide-y divide-[#232323] bg-[#181818]">{children}</tbody>
        ),
        tr: ({ children }) => (
          <tr className="hover:bg-[#222] transition-colors">{children}</tr>
        ),
        th: ({ children }) => (
          <th className="px-5 py-3 text-left text-xs font-semibold text-[#8e8ea0] uppercase tracking-wider border-b border-[#2a2a2a] whitespace-nowrap">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-5 py-3 text-[#d4d4d4] align-top leading-relaxed border-b border-[#1e1e1e]">{children}</td>
        ),

        // Links — section-ref: is an internal pill link produced by preprocessSectionRefs
        a: ({ href, children }) => {
          if (href?.startsWith("section-ref:")) {
            const section = href.replace("section-ref:", "");
            return <SectionRef section={section} act={act} />;
          }
          return (
            <a href={href} target="_blank" rel="noopener noreferrer"
              className="text-[#a78bfa] underline underline-offset-2 hover:text-white transition-colors">
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
