import { useState, type FormEvent, type ReactElement } from "react";

import { answerRules, searchRules } from "../api/client";
import type {
  RuleAnswerResponse,
  RuleCitation,
  RuleFilters,
} from "../api/types";

const ABSTAIN_TEXT = "现有资料不足，无法给出有引用的回答。";

export function RulesPage(): ReactElement {
  const [question, setQuestion] = useState("");
  const [filters, setFilters] = useState<RuleFilters>({});
  const [results, setResults] = useState<RuleCitation[]>([]);
  const [answer, setAnswer] = useState<RuleAnswerResponse | null>(null);
  const [busy, setBusy] = useState<"search" | "answer" | null>(null);
  const [error, setError] = useState("");

  function updateFilter(key: keyof RuleFilters, value: string): void {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy("search");
    setError("");
    setAnswer(null);
    try {
      const response = await searchRules(question.trim(), filters);
      setResults(response.results);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "规则检索失败");
      setResults([]);
    } finally {
      setBusy(null);
    }
  }

  async function handleAnswer(): Promise<void> {
    if (!question.trim()) return;
    setBusy("answer");
    setError("");
    try {
      const response = await answerRules(question.trim(), filters);
      setAnswer(response);
      setResults(response.citations);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "本地回答失败");
      setAnswer(null);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rules-workspace">
      <header className="rules-intro">
        <div>
          <p className="eyebrow">GROUNDED LOCAL RULES</p>
          <h2>有据可查的规则检索</h2>
          <p>
            默认只检索核心规则与调查员手册。扩展或旧版资料必须在“来源包”中明确填写后才会启用。
          </p>
        </div>
        <span className="evidence-badge">本机索引 · 严格引用</span>
      </header>

      <form className="rules-query" onSubmit={handleSearch}>
        <label className="rules-question">
          规则问题
          <textarea
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：困难成功如何判定？"
            required
            rows={3}
            value={question}
          />
        </label>
        <div className="rules-filters">
          <label>
            来源包
            <input
              onChange={(event) => updateFilter("sourcePack", event.target.value)}
              placeholder="留空使用默认权威资料"
              value={filters.sourcePack ?? ""}
            />
          </label>
          <label>
            版本
            <input
              onChange={(event) => updateFilter("edition", event.target.value)}
              placeholder="例如 7e"
              value={filters.edition ?? ""}
            />
          </label>
          <label>
            模块
            <input
              onChange={(event) => updateFilter("module", event.target.value)}
              placeholder="例如 core"
              value={filters.module ?? ""}
            />
          </label>
          <label>
            时代
            <input
              onChange={(event) => updateFilter("era", event.target.value)}
              placeholder="例如 1920s"
              value={filters.era ?? ""}
            />
          </label>
        </div>
        <div className="rules-actions">
          <button disabled={busy !== null || !question.trim()} type="submit">
            {busy === "search" ? "正在检索…" : "检索规则"}
          </button>
          <button
            className="secondary-action"
            disabled={busy !== null || !question.trim()}
            onClick={handleAnswer}
            type="button"
          >
            {busy === "answer" ? "本地模型整理中…" : "依据资料回答"}
          </button>
          <small>回答由 qwen3:30b-instruct 在本机生成；没有有效引用时会拒答。</small>
        </div>
      </form>

      {error ? <p className="rules-error" role="alert">{error}</p> : null}

      {answer ? (
        <article className={answer.abstained ? "grounded-answer abstained" : "grounded-answer"}>
          <span>{answer.abstained ? "证据不足" : "引用已校验"}</span>
          <h3>规则回答</h3>
          <p>{answer.abstained ? ABSTAIN_TEXT : answer.answer}</p>
        </article>
      ) : null}

      <div className="citation-list" aria-live="polite">
        {results.map((citation, index) => (
          <CitationCard citation={citation} index={index + 1} key={citation.citation_id} />
        ))}
        {!busy && !answer && results.length === 0 ? (
          <p className="rules-empty">输入问题开始检索；这里会显示短摘录和精确来源位置。</p>
        ) : null}
      </div>
    </section>
  );
}

function CitationCard({
  citation,
  index,
}: {
  citation: RuleCitation;
  index: number;
}): ReactElement {
  const pageLabel = citation.page === null ? "页码未提供" : `第 ${citation.page} 页`;
  return (
    <article className="citation-card">
      <header>
        <span>证据 {index}</span>
        <small>相似度 {citation.score.toFixed(3)}</small>
      </header>
      <p>{citation.excerpt}</p>
      <footer>
        <strong>{citation.filename}</strong>
        <span>{pageLabel} · {citation.section}</span>
        <span>{citation.edition} · {citation.module} · {citation.source_pack}</span>
      </footer>
    </article>
  );
}
