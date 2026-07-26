import { useEffect, useMemo, useState, type ReactElement } from "react";

import {
  ApiError,
  applyInjury,
  applyRecovery,
  applySanityLoss,
  listCampaigns,
  listInvestigators,
  listRuleOperations,
  resolveRoll,
} from "../api/client";
import type {
  Campaign,
  EngineOperation,
  Investigator,
  RuleOperationLog,
} from "../api/types";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return `本地 API 返回 ${error.status}：${error.message}`;
  }
  return error instanceof Error ? error.message : "发生未知错误";
}

function citationLabel(operation: EngineOperation | RuleOperationLog): string {
  const citation = operation.citation;
  return `${citation.filename} · 第 ${citation.page} 页 · ${citation.section}`;
}

export function SanityInjuryPage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [investigators, setInvestigators] = useState<Investigator[]>([]);
  const [investigatorId, setInvestigatorId] = useState("");
  const [loss, setLoss] = useState(1);
  const [damage, setDamage] = useState(1);
  const [reason, setReason] = useState("现场冲击");
  const [sessionKey, setSessionKey] = useState("本次团务");
  const [logs, setLogs] = useState<RuleOperationLog[]>([]);
  const [latest, setLatest] = useState<EngineOperation | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = useMemo(
    () => investigators.find((item) => item.investigator_id === investigatorId),
    [investigatorId, investigators],
  );

  useEffect(() => {
    const controller = new AbortController();
    listCampaigns(controller.signal)
      .then((items) => {
        setCampaigns(items);
        setCampaignId((current) => current || items[0]?.campaign_id || "");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailure(errorMessage(error));
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!campaignId) {
      setInvestigators([]);
      setLogs([]);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      listInvestigators(campaignId, controller.signal),
      listRuleOperations(campaignId, controller.signal),
    ])
      .then(([people, entries]) => {
        setInvestigators(people);
        setInvestigatorId((current) =>
          people.some((item) => item.investigator_id === current)
            ? current
            : people[0]?.investigator_id || "",
        );
        setLogs(entries);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailure(errorMessage(error));
        }
      });
    return () => controller.abort();
  }, [campaignId]);

  async function execute(
    action: "sanity" | "injury" | "recovery",
  ): Promise<void> {
    if (!selected) {
      setFailure("请先选择调查员。");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const intelligenceCheck =
        action === "sanity" && loss >= 5
          ? await resolveRoll({
              campaign_id: campaignId,
              investigator_id: selected.investigator_id,
              label: "理智损失后的 INT 检定",
              target: selected.profile.characteristics.intelligence,
              difficulty: "regular",
              bonus_penalty: 0,
            })
          : null;
      const result =
        action === "sanity"
          ? await applySanityLoss(campaignId, selected.investigator_id, {
              expected_version: selected.version,
              loss,
              reason,
              session_key: sessionKey,
              intelligence_check_passed: intelligenceCheck?.passed,
            })
          : action === "injury"
            ? await applyInjury(campaignId, selected.investigator_id, {
                expected_version: selected.version,
                damage,
                reason,
                session_key: sessionKey,
              })
            : await applyRecovery(campaignId, selected.investigator_id, {
                expected_version: selected.version,
                care_type: "first_aid",
                session_key: sessionKey,
              });
      setLatest(result);
      setInvestigators((items) =>
        items.map((item) =>
          item.investigator_id === result.investigator.investigator_id
            ? result.investigator
            : item,
        ),
      );
      setLogs(await listRuleOperations(campaignId));
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="engine-workspace">
      <header className="workspace-toolbar">
        <div>
          <p className="eyebrow">DETERMINISTIC COC7 ENGINE</p>
          <h2>理智、疯狂与伤势</h2>
        </div>
        <div className="toolbar-controls">
          <label>
            调查
            <select value={campaignId} onChange={(event) => setCampaignId(event.target.value)}>
              <option value="">请选择</option>
              {campaigns.map((campaign) => (
                <option key={campaign.campaign_id} value={campaign.campaign_id}>
                  {campaign.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            调查员
            <select
              value={investigatorId}
              onChange={(event) => setInvestigatorId(event.target.value)}
            >
              <option value="">请选择</option>
              {investigators.map((investigator) => (
                <option key={investigator.investigator_id} value={investigator.investigator_id}>
                  {investigator.profile.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {failure ? <p className="message error-message">{failure}</p> : null}
      <div className="engine-grid">
        <article className="engine-panel">
          <h3>状态与操作</h3>
          <p className="engine-summary">
            {selected
              ? `理智 ${selected.sanity} · HP ${selected.hit_points} · 状态：${
                  selected.conditions.join("、") || "稳定"
                }`
              : "创建并选择调查员后可执行规则操作。"}
          </p>
          <label className="field">
            <span>团务／日记录键</span>
            <input value={sessionKey} onChange={(event) => setSessionKey(event.target.value)} />
          </label>
          <label className="field">
            <span>原因</span>
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="engine-form-row">
            <label className="field">
              <span>理智损失</span>
              <input
                min="0"
                type="number"
                value={loss}
                onChange={(event) => setLoss(Number(event.target.value))}
              />
            </label>
            <button disabled={busy || !selected} onClick={() => void execute("sanity")} type="button">
              记录理智损失
            </button>
          </div>
          <div className="engine-form-row">
            <label className="field">
              <span>伤害</span>
              <input
                min="0"
                type="number"
                value={damage}
                onChange={(event) => setDamage(Number(event.target.value))}
              />
            </label>
            <button disabled={busy || !selected} onClick={() => void execute("injury")} type="button">
              记录伤势
            </button>
            <button
              className="secondary-button"
              disabled={busy || !selected}
              onClick={() => void execute("recovery")}
              type="button"
            >
              急救恢复
            </button>
          </div>
          {latest ? (
            <div className="citation-card">
              <strong>本次判定引用</strong>
              <span>{citationLabel(latest)}</span>
              <small>{latest.citation.citation_id}</small>
            </div>
          ) : null}
        </article>

        <article className="engine-panel">
          <h3>规则操作日志</h3>
          <div className="operation-list">
            {logs.length ? (
              [...logs].reverse().map((entry) => (
                <div key={entry.operation_id}>
                  <strong>{entry.operation_type}</strong>
                  <span>{citationLabel(entry)}</span>
                  <small>{new Date(entry.created_at).toLocaleString()}</small>
                </div>
              ))
            ) : (
              <p>尚无理智、伤势或恢复记录。</p>
            )}
          </div>
        </article>
      </div>
    </section>
  );
}
