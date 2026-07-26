import { useEffect, useMemo, useState, type ReactElement } from "react";

import {
  ApiError,
  advanceChase,
  createChase,
  listCampaigns,
  listCaseEntries,
  listChases,
  listInvestigators,
  listRuleOperations,
  listWeapons,
  resolveCombat,
  resolveRoll,
} from "../api/client";
import type {
  Campaign,
  CaseEntry,
  Chase,
  Investigator,
  RuleOperationLog,
  WeaponPolicy,
} from "../api/types";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return `本地 API 返回 ${error.status}：${error.message}`;
  }
  return error instanceof Error ? error.message : "发生未知错误";
}

function citationList(item: Pick<Chase | RuleOperationLog, "citation" | "citations">) {
  return item.citations?.length ? item.citations : [item.citation];
}

export function CombatChasePage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [investigators, setInvestigators] = useState<Investigator[]>([]);
  const [attackerId, setAttackerId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [sessions, setSessions] = useState<CaseEntry[]>([]);
  const [caseSessionId, setCaseSessionId] = useState("");
  const [weapons, setWeapons] = useState<WeaponPolicy[]>([]);
  const [weaponKey, setWeaponKey] = useState("unarmed");
  const [damage, setDamage] = useState(1);
  const [chases, setChases] = useState<Chase[]>([]);
  const [chaseId, setChaseId] = useState("");
  const [pursuerPosition, setPursuerPosition] = useState(0);
  const [fleeingPosition, setFleeingPosition] = useState(2);
  const [escapeDistance, setEscapeDistance] = useState(10);
  const [trackLength, setTrackLength] = useState(10);
  const [actingParticipantId, setActingParticipantId] = useState("");
  const [chaseAction, setChaseAction] = useState<"move" | "hazard">("move");
  const [hazardSkillKey, setHazardSkillKey] = useState("fighting_brawl");
  const [logs, setLogs] = useState<RuleOperationLog[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const attacker = useMemo(
    () => investigators.find((item) => item.investigator_id === attackerId),
    [attackerId, investigators],
  );
  const target = useMemo(
    () => investigators.find((item) => item.investigator_id === targetId),
    [targetId, investigators],
  );
  const activeChase = chases.find((item) => item.chase_id === chaseId) ?? chases[0];

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([listCampaigns(controller.signal), listWeapons(controller.signal)])
      .then(([campaignItems, weaponItems]) => {
        setCampaigns(campaignItems);
        setCampaignId((current) => current || campaignItems[0]?.campaign_id || "");
        setWeapons(weaponItems);
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
      setChases([]);
      setSessions([]);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      listInvestigators(campaignId, controller.signal),
      listChases(campaignId, controller.signal),
      listRuleOperations(campaignId, controller.signal),
      listCaseEntries(campaignId, "sessions", controller.signal),
    ])
      .then(([people, chaseItems, operationItems, sessionEntries]) => {
        setInvestigators(people);
        setAttackerId((current) => people.some((item) => item.investigator_id === current) ? current : people[0]?.investigator_id || "");
        setTargetId((current) => people.some((item) => item.investigator_id === current) ? current : people[1]?.investigator_id || "");
        setChases(chaseItems);
        setChaseId((current) => chaseItems.some((item) => item.chase_id === current) ? current : chaseItems[0]?.chase_id || "");
        setLogs(operationItems);
        setSessions(sessionEntries);
        setCaseSessionId((current) => sessionEntries.some((item) => item.entity_id === current) ? current : sessionEntries[0]?.entity_id || "");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailure(errorMessage(error));
        }
      });
    return () => controller.abort();
  }, [campaignId]);

  async function handleCombat(): Promise<void> {
    if (!caseSessionId) {
      setFailure("请先选择案件场次；战斗结算必须归属到场次。");
      return;
    }
    if (!attacker || !target || attacker.investigator_id === target.investigator_id) {
      setFailure("请选择不同的攻击者和目标。");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const weapon = weapons.find((item) => item.weapon_key === weaponKey);
      if (!weapon) {
        setFailure("请选择有效的 COC7 武器。");
        return;
      }
      const fighting =
        attacker.profile.skills.find((skill) => skill.skill_key === weapon.skill_key)
          ?.current_value ?? (weapon.skill_key.startsWith("firearms_") ? 20 : 25);
      const roll = await resolveRoll({
        campaign_id: campaignId,
        case_session_id: caseSessionId,
        investigator_id: attacker.investigator_id,
        skill_key: weapon.skill_key,
        label: `${weapon.name}攻击`,
        target: fighting,
        difficulty: "regular",
        bonus_penalty: 0,
      });
      const result = await resolveCombat(campaignId, {
        attacker_id: attacker.investigator_id,
        target_id: target.investigator_id,
        target_expected_version: target.version,
        attack_roll_id: roll.roll_id,
        weapon_key: weaponKey,
        rolled_damage: damage,
        case_session_id: caseSessionId,
      });
      setInvestigators((items) =>
        items.map((item) =>
          item.investigator_id === result.investigator.investigator_id
            ? result.investigator
            : item,
        ),
      );
      setLogs(await listRuleOperations(campaignId));
      setNotice(
        result.hit
          ? `命中，造成 ${result.damage_applied ?? 0} 点伤害。`
          : "攻击检定未通过，未造成伤害。",
      );
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  function changeCampaign(nextCampaignId: string): void {
    setCampaignId(nextCampaignId);
    setAttackerId("");
    setTargetId("");
    setCaseSessionId("");
    setChases([]);
    setChaseId("");
    setActingParticipantId("");
  }

  async function handleCreateChase(): Promise<void> {
    if (!caseSessionId) {
      setFailure("建立追逐必须选择案件场次。");
      return;
    }
    if (!attacker || !target || attacker.investigator_id === target.investigator_id) {
      setFailure("建立追逐需要两名不同的参与者。");
      return;
    }
    setBusy(true);
    try {
      const chase = await createChase(campaignId, {
        title: "现场追逐",
        case_session_id: caseSessionId,
        participants: [
          { investigator_id: attacker.investigator_id, role: "pursuer", position: pursuerPosition },
          { investigator_id: target.investigator_id, role: "fleeing", position: fleeingPosition },
        ],
        escape_distance: escapeDistance,
        track_length: trackLength,
      });
      setChases((items) => [chase, ...items]);
      setChaseId(chase.chase_id);
      setActingParticipantId(chase.participants[0]?.investigator_id || "");
      setLogs(await listRuleOperations(campaignId));
      setNotice("追逐已建立。");
      setFailure(null);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleAdvance(): Promise<void> {
    if (!activeChase || !actingParticipantId || activeChase.status !== "active") return;
    setBusy(true);
    try {
      let rollId: string | undefined;
      if (chaseAction === "hazard") {
        const actor = investigators.find((item) => item.investigator_id === actingParticipantId);
        const targetValue = actor?.profile.skills.find((skill) => skill.skill_key === hazardSkillKey)?.current_value;
        if (!actor || targetValue === undefined) throw new Error("行动者没有所选障碍技能。");
        const roll = await resolveRoll({ campaign_id: campaignId, case_session_id: activeChase.case_session_id ?? undefined, investigator_id: actingParticipantId, skill_key: hazardSkillKey, label: "追逐障碍", target: targetValue, difficulty: "regular", bonus_penalty: 0 });
        rollId = roll.roll_id;
      }
      const chase = await advanceChase(campaignId, activeChase.chase_id, {
        expected_version: activeChase.version,
        action: { investigator_id: actingParticipantId, action: chaseAction, roll_id: rollId, skill_key: chaseAction === "hazard" ? hazardSkillKey : undefined },
      });
      setChases((items) =>
        items.map((item) => (item.chase_id === chase.chase_id ? chase : item)),
      );
      setLogs(await listRuleOperations(campaignId));
      setNotice("已记录一项追逐行动。");
      setFailure(null);
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
          <p className="eyebrow">COMBAT & CHASE · COC7</p>
          <h2>战斗与追逐记录台</h2>
        </div>
        <label className="field">
          <span>调查</span>
          <select value={campaignId} onChange={(event) => changeCampaign(event.target.value)}>
            <option value="">请选择</option>
            {campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>案件场次</span>
          <select value={caseSessionId} onChange={(event) => setCaseSessionId(event.target.value)}>
            <option value="">请选择</option>
            {sessions.map((session) => <option key={session.entity_id} value={session.entity_id}>{session.title}</option>)}
          </select>
        </label>
      </header>
      {failure ? <p className="message error-message">{failure}</p> : null}
      {notice ? <p className="message success-message">{notice}</p> : null}
      <div className="engine-grid">
        <article className="engine-panel">
          <h3>战斗结算</h3>
          <div className="engine-form-grid">
            <label className="field">
              <span>攻击者</span>
              <select value={attackerId} onChange={(event) => setAttackerId(event.target.value)}>
                <option value="">请选择</option>
                {investigators.map((item) => (
                  <option key={item.investigator_id} value={item.investigator_id}>
                    {item.profile.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>目标</span>
              <select value={targetId} onChange={(event) => setTargetId(event.target.value)}>
                <option value="">请选择</option>
                {investigators.map((item) => (
                  <option key={item.investigator_id} value={item.investigator_id}>
                    {item.profile.name} · HP {item.hit_points}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>武器</span>
              <select value={weaponKey} onChange={(event) => setWeaponKey(event.target.value)}>
                {weapons.map((weapon) => (
                  <option key={weapon.weapon_key} value={weapon.weapon_key}>
                    {weapon.name} · {weapon.damage_notation}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>已掷伤害</span>
              <input
                min="0"
                type="number"
                value={damage}
                onChange={(event) => setDamage(Number(event.target.value))}
              />
            </label>
          </div>
          <button disabled={busy || !attacker || !target || !caseSessionId} onClick={() => void handleCombat()} type="button">
            结算攻击
          </button>
          <p className="section-help">
            系统先写入百分骰攻击记录，再按内置 COC7 武器策略结算伤害与重伤。
          </p>
        </article>

        <article className="engine-panel">
          <h3>追逐</h3>
          <div className="engine-form-grid">
            <label className="field"><span>追者起点</span><input type="number" min="0" value={pursuerPosition} onChange={(event) => setPursuerPosition(Number(event.target.value))} /></label>
            <label className="field"><span>逃者起点</span><input type="number" min="0" value={fleeingPosition} onChange={(event) => setFleeingPosition(Number(event.target.value))} /></label>
            <label className="field"><span>逃脱距离</span><input type="number" min="1" value={escapeDistance} onChange={(event) => setEscapeDistance(Number(event.target.value))} /></label>
            <label className="field"><span>赛道长度</span><input type="number" min="1" value={trackLength} onChange={(event) => setTrackLength(Number(event.target.value))} /></label>
          </div>
          <div className="engine-actions">
            <button disabled={busy || investigators.length < 2 || !caseSessionId} onClick={() => void handleCreateChase()} type="button">
              建立追逐
            </button>
          </div>
          {activeChase ? (
            <div className="chase-track">
              <label className="field"><span>选择追逐</span><select value={activeChase.chase_id} onChange={(event) => setChaseId(event.target.value)}>{chases.map((item) => <option key={item.chase_id} value={item.chase_id}>{item.title}</option>)}</select></label>
              <strong>{activeChase.title}</strong>
              <span>第 {activeChase.round} 轮 · {activeChase.status} · 逃脱距离 {activeChase.escape_distance}</span>
              {activeChase.participants.map((participant) => (
                <span key={participant.investigator_id}>
                  {investigators.find(
                    (item) => item.investigator_id === participant.investigator_id,
                  )?.profile.name ?? participant.investigator_id}
                  ：位置 {participant.position}（{participant.role} · MOV {participant.move_rate} · AP {participant.actions_remaining}）
                </span>
              ))}
              {activeChase.status === "active" ? <div className="engine-form-grid">
                <label className="field"><span>行动者</span><select value={actingParticipantId} onChange={(event) => setActingParticipantId(event.target.value)}>{activeChase.participants.map((item) => <option key={item.investigator_id} value={item.investigator_id}>{investigators.find((person) => person.investigator_id === item.investigator_id)?.profile.name ?? item.investigator_id}</option>)}</select></label>
                <label className="field"><span>行动</span><select value={chaseAction} onChange={(event) => setChaseAction(event.target.value as "move" | "hazard")}><option value="move">移动</option><option value="hazard">障碍检定</option></select></label>
                {chaseAction === "hazard" ? <label className="field"><span>障碍技能</span><input value={hazardSkillKey} onChange={(event) => setHazardSkillKey(event.target.value)} /></label> : null}
                <button className="secondary-button" disabled={busy || !actingParticipantId} onClick={() => void handleAdvance()} type="button">执行一项行动</button>
              </div> : null}
              {citationList(activeChase).map((citation) => (
                <small key={citation.citation_id}>
                  {citation.filename} · 第 {citation.page} 页 · {citation.section} · {citation.citation_id}
                </small>
              ))}
            </div>
          ) : (
            <p>尚未建立追逐。</p>
          )}
        </article>
      </div>
      <article className="engine-panel">
        <h3>战斗与追逐日志</h3>
        <div className="operation-list">
          {[...logs]
            .reverse()
            .filter((entry) => entry.operation_type.startsWith("combat") || entry.operation_type.startsWith("chase"))
            .map((entry) => (
              <div key={entry.operation_id}>
                <strong>{entry.operation_type}</strong>
                {citationList(entry).map((citation) => (
                  <span key={citation.citation_id}>
                    {citation.filename} · 第 {citation.page} 页 · {citation.section} · {citation.citation_id}
                  </span>
                ))}
              </div>
            ))}
        </div>
      </article>
    </section>
  );
}
