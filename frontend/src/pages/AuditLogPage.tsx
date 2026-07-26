import { useEffect, useState, type ReactElement } from "react";

import {
  listAIProposalAudits,
  listCampaigns,
  listRuleOperations,
  listStateAudits,
} from "../api/client";
import type {
  Campaign,
  ProposalAuditLog,
  RuleOperationLog,
  StateAuditLog,
} from "../api/types";
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";

export function AuditLogPage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [audits, setAudits] = useState<StateAuditLog[]>([]);
  const [operations, setOperations] = useState<RuleOperationLog[]>([]);
  const [proposalAudits, setProposalAudits] = useState<ProposalAuditLog[]>([]);
  const [view, setView] = useState<"state" | "rules" | "proposals">("state");
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
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : "读取案件失败");
        }
      });
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
      setAudits([]);
      setOperations([]);
      setProposalAudits([]);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      listStateAudits(campaignId, controller.signal),
      listRuleOperations(campaignId, controller.signal),
      listAIProposalAudits(campaignId, controller.signal),
    ])
      .then(([nextAudits, nextOperations, nextProposalAudits]) => {
        setAudits(nextAudits);
        setOperations(nextOperations);
        setProposalAudits(nextProposalAudits);
        setError("");
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : "读取审计日志失败");
        }
      });
    return () => controller.abort();
  }, [campaignId]);

  return (
    <section className="audit-workspace">
      <header className="workspace-toolbar">
        <div>
          <p className="eyebrow">IMMUTABLE LOCAL HISTORY</p>
          <h2>状态与规则审计</h2>
          <p>查看谁在何时改变了案件，以及每次 COC7 判定使用的输入、输出和来源。</p>
        </div>
        <label className="field">
          <span>当前案件</span>
          <select
            value={campaignId}
            onChange={(event) => {
              setCampaignId(event.target.value);
              selectCampaign(event.target.value);
            }}
          >
            <option value="">请选择</option>
            {campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.title}
              </option>
            ))}
          </select>
        </label>
      </header>

      <nav className="audit-tabs" aria-label="审计类型">
        <button
          className={view === "state" ? "active" : ""}
          onClick={() => setView("state")}
          type="button"
        >
          状态变更 · {audits.length}
        </button>
        <button
          className={view === "rules" ? "active" : ""}
          onClick={() => setView("rules")}
          type="button"
        >
          规则操作 · {operations.length}
        </button>
        <button
          className={view === "proposals" ? "active" : ""}
          onClick={() => setView("proposals")}
          type="button"
        >
          AI 提案裁决 · {proposalAudits.length}
        </button>
      </nav>

      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {!campaignId ? <p className="case-empty">先选择一个案件。</p> : null}

      <div className="audit-list">
        {view === "state"
          ? audits.map((entry) => (
              <article key={entry.audit_id}>
                <header>
                  <div>
                    <strong>{entry.action}</strong>
                    <span>{entry.entity_type} · {entry.entity_id}</span>
                  </div>
                  <time>{new Date(entry.created_at).toLocaleString()}</time>
                </header>
                <details>
                  <summary>查看变更前后</summary>
                  <div className="audit-diff">
                    <pre>{JSON.stringify(entry.before, null, 2)}</pre>
                    <pre>{JSON.stringify(entry.after, null, 2)}</pre>
                  </div>
                </details>
              </article>
            ))
          : view === "rules"
            ? operations.map((entry) => (
              <article key={entry.operation_id}>
                <header>
                  <div>
                    <strong>{entry.operation_type}</strong>
                    <span>{entry.subject_id}</span>
                  </div>
                  <time>{new Date(entry.created_at).toLocaleString()}</time>
                </header>
                <p>
                  {entry.citations.map((citation) =>
                    `${citation.filename} 第${citation.page}页`,
                  ).join(" · ")}
                </p>
                <details>
                  <summary>查看判定输入与输出</summary>
                  <div className="audit-diff">
                    <pre>{JSON.stringify(entry.input_data, null, 2)}</pre>
                    <pre>{JSON.stringify(entry.output_data, null, 2)}</pre>
                  </div>
                </details>
              </article>
            ))
            : proposalAudits.map((entry) => (
              <article key={entry.audit_id}>
                <header>
                  <div>
                    <strong>{entry.action === "confirm" ? "确认提案" : "拒绝提案"}</strong>
                    <span>提案 {entry.proposal_id} · 预期版本 v{entry.expected_version}</span>
                  </div>
                  <time>{new Date(entry.created_at).toLocaleString()}</time>
                </header>
                {entry.reason ? <p>原因：{entry.reason}</p> : null}
                <details>
                  <summary>查看裁决前后</summary>
                  <div className="audit-diff">
                    <pre>{JSON.stringify(entry.before, null, 2)}</pre>
                    <pre>{JSON.stringify(entry.after, null, 2)}</pre>
                  </div>
                </details>
              </article>
            ))}
      </div>
    </section>
  );
}
