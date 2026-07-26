import { useEffect, useState, type ReactElement } from "react";

import {
  askAIKP,
  decideAIProposal,
  listAIProposals,
  listCampaigns,
} from "../api/client";
import type {
  AIKPResponse,
  AIProposal,
  Campaign,
} from "../api/types";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";

export function AIKPPage({
  initialView,
}: {
  initialView: "assistant" | "proposals";
}): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<
    "answer" | "private_hint" | "scenario_draft"
  >("private_hint");
  const [result, setResult] = useState<AIKPResponse | null>(null);
  const [proposals, setProposals] = useState<AIProposal[]>([]);
  const [rejectionReason, setRejectionReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    listCampaigns(controller.signal)
      .then((items) => {
        setCampaigns(items);
        const selected = chooseAvailableCampaign(
          items.map((item) => item.campaign_id),
          "",
        );
        setCampaignId(selected);
        selectCampaign(selected);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(
    () =>
      subscribeToCampaignSelection((nextCampaignId) => {
        setCampaignId((current) =>
          current === nextCampaignId ? current : nextCampaignId,
        );
      }),
    [],
  );

  useEffect(() => {
    if (!campaignId) {
      setProposals([]);
      return;
    }
    const controller = new AbortController();
    listAIProposals(campaignId, controller.signal)
      .then(setProposals)
      .catch(() => undefined);
    return () => controller.abort();
  }, [campaignId, initialView]);

  async function ask(): Promise<void> {
    if (!campaignId || !question.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await askAIKP(campaignId, {
        question: question.trim(),
        mode,
      });
      setResult(response);
      setProposals(await listAIProposals(campaignId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "本地模型调用失败");
    } finally {
      setBusy(false);
    }
  }

  async function decide(
    proposal: AIProposal,
    decision: "confirm" | "reject",
  ): Promise<void> {
    if (decision === "reject" && !rejectionReason.trim()) {
      setError("拒绝提案前请填写原因。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await decideAIProposal(campaignId, proposal.proposal_id, {
        expected_version: proposal.version,
        decision,
        ...(decision === "reject" ? { reason: rejectionReason.trim() } : {}),
      });
      setProposals(await listAIProposals(campaignId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提案处理失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ai-kp-workspace">
      <section className="ai-kp-heading">
        <div>
          <p className="eyebrow">LOCAL QWEN · READ-ONLY ORCHESTRATION</p>
          <h2>
            {initialView === "assistant"
              ? "AI KP 私密工作台"
              : "待确认提案中心"}
          </h2>
          <p>
            {initialView === "assistant"
              ? "读取规则证据与案件私密上下文，整理 KP 提示、场景建议和结构化草案。"
              : "逐项查看模型草案、引用证据与字段差异；确认前不会写入案件资料。"}
          </p>
        </div>
        <span className="advisory-badge">模型建议尚未生效</span>
      </section>

      <label className="ai-kp-case-picker">
        当前案件
        <select
          value={campaignId}
          onChange={(event) => {
            setCampaignId(event.target.value);
            selectCampaign(event.target.value);
          }}
        >
          <option value="">请选择案件</option>
          {campaigns.map((campaign) => (
            <option key={campaign.campaign_id} value={campaign.campaign_id}>
              {campaign.title}
            </option>
          ))}
        </select>
      </label>

      {initialView === "assistant" ? (
        <section className="ai-kp-console">
          <label>
            工作模式
            <select
              value={mode}
              onChange={(event) =>
                setMode(event.target.value as typeof mode)
              }
            >
              <option value="answer">证据问答</option>
              <option value="private_hint">KP 私密提示</option>
              <option value="scenario_draft">场景／线索／人物草案</option>
            </select>
          </label>
          <label>
            给副驾驶的任务
            <textarea
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：调查员已经找到航海日志，下一幕如何推进？"
              rows={5}
              value={question}
            />
          </label>
          <button
            disabled={busy || !campaignId || !question.trim()}
            onClick={() => void ask()}
            type="button"
          >
            {busy ? "本地模型处理中…" : "生成建议"}
          </button>
          {result ? (
            <article className="ai-kp-result">
              <h3>副驾驶建议</h3>
              <p>{result.answer || "未提供直接回答。"}</p>
              <h3>KP 私密提示</h3>
              <ul>
                {result.keeper_private_hints.map((hint) => <li key={hint}>{hint}</li>)}
              </ul>
              <h3>场景建议</h3>
              <ul>
                {result.scene_suggestions.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <h3>规则与证据引用</h3>
              {result.citations.length ? (
                <div className="ai-kp-citations">
                  {result.citations.map((citation, index) => (
                    <article key={`${String(citation.citation_id ?? "citation")}-${index}`}>
                      <strong>
                        {String(citation.filename ?? "本地规则资料")}
                        {citation.page ? ` · 第 ${String(citation.page)} 页` : ""}
                      </strong>
                      <span>{String(citation.section ?? "未标章节")}</span>
                      {citation.excerpt ? <p>{String(citation.excerpt)}</p> : null}
                    </article>
                  ))}
                </div>
              ) : (
                <p className="proposal-evidence">本次建议只使用案件上下文，未引用规则片段。</p>
              )}
              <small>
                {result.model_name} · {result.proposals.length} 项待确认提案
              </small>
            </article>
          ) : null}
        </section>
      ) : (
        <section className="proposal-center">
          <label>
            拒绝原因
            <input
              onChange={(event) => setRejectionReason(event.target.value)}
              placeholder="拒绝提案时必填"
              value={rejectionReason}
            />
          </label>
          {campaignId && proposals.length === 0 ? (
            <p className="case-empty">当前案件没有 AI 提案。</p>
          ) : null}
          {proposals.map((proposal) => (
            <article className="proposal-card" key={proposal.proposal_id}>
              <header>
                <div>
                  <strong>{proposal.case_kind} · {proposal.proposal_type}</strong>
                  <small>v{proposal.version} · {proposal.model_name}</small>
                </div>
                <span className={`proposal-status ${proposal.status}`}>
                  {proposal.status === "pending" && proposal.is_expired
                    ? "已过期"
                    : proposal.status === "pending"
                    ? "待确认"
                    : proposal.status === "confirmed"
                      ? "已确认"
                      : "已拒绝"}
                </span>
              </header>
              <h3>字段差异／拟写入内容</h3>
              <pre>{JSON.stringify(proposal.diff, null, 2)}</pre>
              <h3>证据</h3>
              {proposal.evidence.length ? (
                proposal.evidence.map((item, index) => (
                  <p className="proposal-evidence" key={`${proposal.proposal_id}-${index}`}>
                    {String(item.filename ?? "案件上下文")} ·
                    {item.page ? ` 第 ${String(item.page)} 页` : " 无页码"} ·
                    {String(item.section ?? "未标章节")}
                  </p>
                ))
              ) : (
                <p className="proposal-evidence">仅依据当前案件上下文，无规则引用。</p>
              )}
              <p className="proposal-evidence">
                有效期至 {new Date(proposal.expires_at).toLocaleString()}
              </p>
              {proposal.status === "pending" && !proposal.is_expired ? (
                <div className="proposal-actions">
                  <button disabled={busy} onClick={() => void decide(proposal, "confirm")} type="button">
                    确认并写入
                  </button>
                  <button disabled={busy} onClick={() => void decide(proposal, "reject")} type="button">
                    拒绝
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </section>
      )}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}
