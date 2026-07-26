import { useEffect, useMemo, useState, type ReactElement } from "react";

import {
  ApiError,
  applyInjury,
  applyRecovery,
  applySanityLoss,
  listCampaigns,
  listCaseEntries,
  listInvestigators,
  listRuleOperations,
  resolveRoll,
} from "../api/client";
import type {
  Campaign,
  CaseEntry,
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

function citationLabel(citation: EngineOperation["citation"]): string {
  return `${citation.filename} · 第 ${citation.page} 页 · ${citation.section}`;
}

function citationList(operation: EngineOperation | RuleOperationLog): EngineOperation["citation"][] {
  return operation.citations?.length ? operation.citations : [operation.citation];
}

export function SanityInjuryPage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [investigators, setInvestigators] = useState<Investigator[]>([]);
  const [investigatorId, setInvestigatorId] = useState("");
  const [sessions, setSessions] = useState<CaseEntry[]>([]);
  const [caseSessionId, setCaseSessionId] = useState("");
  const [loss, setLoss] = useState(1);
  const [damage, setDamage] = useState(1);
  const [reason, setReason] = useState("现场冲击");
  const [sessionKey, setSessionKey] = useState("本次团务");
  const [careType, setCareType] = useState<"first_aid" | "medicine" | "natural">("first_aid");
  const [healingRoll, setHealingRoll] = useState(1);
  const [periodKey, setPeriodKey] = useState("本日");
  const [injuryId, setInjuryId] = useState("");
  const [logs, setLogs] = useState<RuleOperationLog[]>([]);
  const [latest, setLatest] = useState<EngineOperation | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = useMemo(
    () => investigators.find((item) => item.investigator_id === investigatorId),
    [investigatorId, investigators],
  );

  const latestInjuryId = useMemo(() => {
    const injury = [...logs].reverse().find(
      (entry) => entry.operation_type === "injury" && entry.subject_id === investigatorId,
    );
    const value = injury?.output_data.injury_id;
    return typeof value === "string" ? value : "";
  }, [investigatorId, logs]);

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
      setSessions([]);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      listInvestigators(campaignId, controller.signal),
      listRuleOperations(campaignId, controller.signal),
      listCaseEntries(campaignId, "sessions", controller.signal),
    ])
      .then(([people, entries, sessionEntries]) => {
        setInvestigators(people);
        setInvestigatorId((current) =>
          people.some((item) => item.investigator_id === current)
            ? current
            : people[0]?.investigator_id || "",
        );
        setLogs(entries);
        setSessions(sessionEntries);
        setCaseSessionId((current) =>
          sessionEntries.some((entry) => entry.entity_id === current)
            ? current
            : sessionEntries[0]?.entity_id || "",
        );
        setInjuryId("");
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
    if (!caseSessionId) {
      setFailure("请先选择案件场次；规则操作必须归属到场次。");
      return;
    }
    const resolvedInjuryId = injuryId || latestInjuryId;
    if (action === "recovery" && !resolvedInjuryId) {
      setFailure("请先记录并选择一条伤势，再进行恢复。");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const intelligenceCheck =
        action === "sanity" && loss >= 5
          ? await resolveRoll({
              campaign_id: campaignId,
              case_session_id: caseSessionId,
              investigator_id: selected.investigator_id,
              skill_key: "intelligence",
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
              case_session_id: caseSessionId,
              intelligence_roll_id: intelligenceCheck?.roll_id,
            })
          : action === "injury"
            ? await applyInjury(campaignId, selected.investigator_id, {
                expected_version: selected.version,
                damage,
                reason,
                session_key: sessionKey,
                case_session_id: caseSessionId,
              })
            : await applyRecovery(campaignId, selected.investigator_id, {
                expected_version: selected.version,
                care_type: careType,
                injury_id: resolvedInjuryId,
                healing_roll: careType === "first_aid" ? undefined : healingRoll,
                period_key: careType === "natural" ? periodKey : undefined,
                session_key: sessionKey,
                case_session_id: caseSessionId,
                ...(careType === "medicine"
                  ? {
                      medicine_roll_id: (
                        await resolveRoll({
                          campaign_id: campaignId,
                          case_session_id: caseSessionId,
                          investigator_id: selected.investigator_id,
                          skill_key: "medicine",
                          label: "医学恢复检定",
                          target:
                            selected.profile.skills.find((skill) => skill.skill_key === "medicine")
                              ?.current_value ?? 1,
                          difficulty: "regular",
                          bonus_penalty: 0,
                        })
                      ).roll_id,
                    }
                  : careType === "natural"
                    ? {
                        constitution_roll_id: (
                          await resolveRoll({
                            campaign_id: campaignId,
                            case_session_id: caseSessionId,
                            investigator_id: selected.investigator_id,
                            skill_key: "constitution",
                            label: "自然恢复 CON 检定",
                            target: selected.profile.characteristics.constitution,
                            difficulty: "regular",
                            bonus_penalty: 0,
                          })
                        ).roll_id,
                      }
                    : {}),
              });
      setLatest(result);
      if (action === "injury" && result.injury_id) setInjuryId(result.injury_id);
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

  function changeCampaign(nextCampaignId: string): void {
    setCampaignId(nextCampaignId);
    setInvestigatorId("");
    setCaseSessionId("");
    setInjuryId("");
    setLatest(null);
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
            <select value={campaignId} onChange={(event) => changeCampaign(event.target.value)}>
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
            <span>案件场次</span>
            <select value={caseSessionId} onChange={(event) => setCaseSessionId(event.target.value)}>
              <option value="">请选择</option>
              {sessions.map((session) => (
                <option key={session.entity_id} value={session.entity_id}>{session.title}</option>
              ))}
            </select>
          </label>
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
          </div>
          <div className="engine-form-grid">
            <label className="field">
              <span>要恢复的伤势</span>
              <select value={injuryId || latestInjuryId} onChange={(event) => setInjuryId(event.target.value)}>
                <option value="">请选择伤势</option>
                {latestInjuryId ? <option value={latestInjuryId}>最近伤势</option> : null}
              </select>
            </label>
            <label className="field">
              <span>恢复方式</span>
              <select value={careType} onChange={(event) => setCareType(event.target.value as typeof careType)}>
                <option value="first_aid">急救</option>
                <option value="medicine">医学</option>
                <option value="natural">自然恢复</option>
              </select>
            </label>
            {careType !== "first_aid" ? <label className="field"><span>治疗 1D3（1–3）</span><input min="1" max="3" type="number" value={healingRoll} onChange={(event) => setHealingRoll(Number(event.target.value))} /></label> : null}
            {careType === "natural" ? <label className="field"><span>恢复周期键</span><input value={periodKey} onChange={(event) => setPeriodKey(event.target.value)} /></label> : null}
          </div>
          <button className="secondary-button" disabled={busy || !selected || !caseSessionId} onClick={() => void execute("recovery")} type="button">
            {careType === "first_aid" ? "急救恢复" : careType === "medicine" ? "医学恢复（掷医学）" : "自然恢复（掷 CON）"}
          </button>
          {latest ? (
            <div className="citation-card">
              <strong>本次判定引用</strong>
              {citationList(latest).map((citation) => (
                <span key={citation.citation_id}>{citationLabel(citation)} · {citation.citation_id}</span>
              ))}
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
                  {citationList(entry).map((citation) => (
                    <span key={citation.citation_id}>{citationLabel(citation)} · {citation.citation_id}</span>
                  ))}
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
