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
import {
  chooseAvailableCampaign,
  selectCampaign,
  subscribeToCampaignSelection,
} from "../state/campaignSelection";

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
  const [pursuerId, setPursuerId] = useState("");
  const [fleeingId, setFleeingId] = useState("");
  const [sessions, setSessions] = useState<CaseEntry[]>([]);
  const [caseSessionId, setCaseSessionId] = useState("");
  const [weapons, setWeapons] = useState<WeaponPolicy[]>([]);
  const [weaponKey, setWeaponKey] = useState("unarmed");
  const [damage, setDamage] = useState(1);
  const [manualAttackRoll, setManualAttackRoll] = useState("");
  const [combatParticipantIds, setCombatParticipantIds] = useState<string[]>([]);
  const [turnOrderIds, setTurnOrderIds] = useState<string[]>([]);
  const [turnIndex, setTurnIndex] = useState(0);
  const [combatRound, setCombatRound] = useState(1);
  const [combatActive, setCombatActive] = useState(false);
  const [turnResolved, setTurnResolved] = useState(false);
  const [combatNotes, setCombatNotes] = useState<string[]>([]);
  const [logsCollapsed, setLogsCollapsed] = useState(false);
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
  const pursuer = useMemo(
    () => investigators.find((item) => item.investigator_id === pursuerId),
    [investigators, pursuerId],
  );
  const fleeing = useMemo(
    () => investigators.find((item) => item.investigator_id === fleeingId),
    [fleeingId, investigators],
  );
  const activeCombatantId = combatActive ? turnOrderIds[turnIndex] : undefined;
  const activeCombatant = investigators.find(
    (item) => item.investigator_id === activeCombatantId,
  );
  const selectedWeapon = weapons.find((item) => item.weapon_key === weaponKey);
  const attackSkillValue = attacker && selectedWeapon
    ? attacker.profile.skills.find((skill) => skill.skill_key === selectedWeapon.skill_key)
      ?.current_value ?? (selectedWeapon.skill_key.startsWith("firearms_") ? 20 : 25)
    : 0;
  const activeChase = chases.find((item) => item.chase_id === chaseId) ?? chases[0];

  useEffect(() => {
    if (!activeChase) {
      setActingParticipantId("");
      return;
    }
    setActingParticipantId((current) =>
      activeChase.participants.some((item) => item.investigator_id === current)
        ? current
        : activeChase.participants[0]?.investigator_id || "",
    );
  }, [activeChase]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([listCampaigns(controller.signal), listWeapons(controller.signal)])
      .then(([campaignItems, weaponItems]) => {
        setCampaigns(campaignItems);
        const selected = chooseAvailableCampaign(
          campaignItems.map((item) => item.campaign_id),
          "",
        );
        setCampaignId(selected);
        selectCampaign(selected);
        setWeapons(weaponItems);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailure(errorMessage(error));
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
        setCombatParticipantIds(people.map((item) => item.investigator_id));
        setAttackerId((current) => people.some((item) => item.investigator_id === current) ? current : people[0]?.investigator_id || "");
        setTargetId((current) => people.some((item) => item.investigator_id === current) ? current : people[1]?.investigator_id || "");
        setPursuerId((current) => people.some((item) => item.investigator_id === current) ? current : people[0]?.investigator_id || "");
        setFleeingId((current) => people.some((item) => item.investigator_id === current) ? current : people[1]?.investigator_id || "");
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
    if (combatActive && attacker.investigator_id !== activeCombatantId) {
      setFailure("只能由当前行动者结算攻击；请先结束上一名参与者的回合。");
      return;
    }
    if (combatActive && turnResolved) {
      setFailure("当前行动者已经完成本轮主要行动，请结束其回合。");
      return;
    }
    if (manualAttackRoll && (!Number.isInteger(Number(manualAttackRoll)) || Number(manualAttackRoll) < 1 || Number(manualAttackRoll) > 100)) {
      setFailure("玩家 D100 结果必须是 1 到 100 的整数。");
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
        dice: manualAttackRoll
          ? {
            units_digit: Number(manualAttackRoll) === 100 ? 0 : Number(manualAttackRoll) % 10,
            tens_digits: [Number(manualAttackRoll) === 100 ? 0 : Math.floor(Number(manualAttackRoll) / 10)],
          }
          : undefined,
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
      const weaponName = weapon.name;
      setCombatNotes((items) => [
        `第 ${combatRound} 轮：${attacker.profile.name} 使用${weaponName}攻击 ${target.profile.name}；D100=${roll.roll}，需要 ≤${fighting}（困难 ≤${Math.floor(fighting / 2)}，极难 ≤${Math.floor(fighting / 5)}）；${result.hit ? `命中并造成 ${result.damage_applied ?? 0} 点伤害` : "未命中"}。`,
        ...items,
      ]);
      setTurnResolved(true);
      setManualAttackRoll("");
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

  function toggleCombatParticipant(investigatorId: string): void {
    if (combatActive) return;
    setCombatParticipantIds((items) =>
      items.includes(investigatorId)
        ? items.filter((item) => item !== investigatorId)
        : [...items, investigatorId],
    );
  }

  function startCombat(): void {
    const order = investigators
      .filter((item) => combatParticipantIds.includes(item.investigator_id) && !item.conditions.includes("dead"))
      .sort((left, right) => right.profile.characteristics.dexterity - left.profile.characteristics.dexterity)
      .map((item) => item.investigator_id);
    if (!caseSessionId) {
      setFailure("请先选择案件场次。战斗回合必须归属到明确的跑团记录。");
      return;
    }
    if (order.length < 2) {
      setFailure("至少选择两名未死亡的参与者才能开始战斗。");
      return;
    }
    setTurnOrderIds(order);
    setTurnIndex(0);
    setCombatRound(1);
    setCombatActive(true);
    setTurnResolved(false);
    setAttackerId(order[0]);
    setTargetId(order.find((id) => id !== order[0]) ?? "");
    setCombatNotes(["战斗开始：按 DEX 从高到低排列行动顺序；枪械先发、突袭和特殊情况由 KP 按规则裁定。"]);
    setFailure(null);
    setNotice("战斗回合台已开始。");
  }

  function endTurn(): void {
    if (!combatActive || turnOrderIds.length === 0) return;
    const nextIndex = (turnIndex + 1) % turnOrderIds.length;
    const nextRound = nextIndex === 0 ? combatRound + 1 : combatRound;
    const nextId = turnOrderIds[nextIndex];
    setTurnIndex(nextIndex);
    setCombatRound(nextRound);
    setTurnResolved(false);
    setAttackerId(nextId);
    setTargetId((current) => current !== nextId ? current : turnOrderIds.find((id) => id !== nextId) ?? "");
    const name = investigators.find((item) => item.investigator_id === nextId)?.profile.name ?? nextId;
    setCombatNotes((items) => [`第 ${nextRound} 轮：轮到 ${name}。`, ...items]);
    setFailure(null);
  }

  function resetCombat(): void {
    setCombatActive(false);
    setTurnOrderIds([]);
    setTurnIndex(0);
    setCombatRound(1);
    setTurnResolved(false);
    setManualAttackRoll("");
    setCombatNotes([]);
    setNotice("战斗回合台已重置。已写入的伤害和规则日志不会被撤销。");
    setFailure(null);
  }

  function changeCampaign(nextCampaignId: string): void {
    setCampaignId(nextCampaignId);
    selectCampaign(nextCampaignId);
    setAttackerId("");
    setTargetId("");
    setPursuerId("");
    setFleeingId("");
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
    if (investigators.length < 2) {
      setFailure("当前案件至少需要两名调查员才能建立追逐；请先在调查员界面创建第二名参与者。");
      return;
    }
    if (!pursuer || !fleeing || pursuer.investigator_id === fleeing.investigator_id) {
      setFailure("请选择两名不同的追逐参与者，并分别指定追逐者与逃亡者。");
      return;
    }
    setBusy(true);
    try {
      const chase = await createChase(campaignId, {
        title: "现场追逐",
        case_session_id: caseSessionId,
        participants: [
          { investigator_id: pursuer.investigator_id, role: "pursuer", position: pursuerPosition },
          { investigator_id: fleeing.investigator_id, role: "fleeing", position: fleeingPosition },
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
          <div className="combat-heading">
            <div>
              <h3>COC7 战斗回合台</h3>
              <p>{combatActive ? `第 ${combatRound} 轮 · 当前行动者：${activeCombatant?.profile.name ?? "未知"}` : "先选择参与者，再按 DEX 建立行动顺序。"}</p>
            </div>
            <div className="engine-actions">
              {!combatActive ? <button disabled={busy || combatParticipantIds.length < 2} onClick={startCombat} type="button">开始战斗</button> : null}
              <button className="secondary-button" disabled={busy || (!combatActive && combatNotes.length === 0)} onClick={resetCombat} type="button">重置战斗</button>
            </div>
          </div>
          <div className="combatant-picker" aria-label="战斗参与者">
            {investigators.map((item) => (
              <button
                className={`combatant-card ${combatParticipantIds.includes(item.investigator_id) ? "selected" : ""} ${activeCombatantId === item.investigator_id ? "active" : ""}`}
                disabled={combatActive}
                key={item.investigator_id}
                onClick={() => toggleCombatParticipant(item.investigator_id)}
                type="button"
              >
                <strong>{item.profile.name}</strong>
                <span>DEX {item.profile.characteristics.dexterity} · HP {item.hit_points} · SAN {item.sanity} · MOV {item.profile.move_rate}</span>
                <small>{item.conditions.length ? item.conditions.join(" · ") : "状态正常"}</small>
              </button>
            ))}
          </div>
          {combatActive ? <div className="turn-order" aria-label="行动顺序">
            {turnOrderIds.map((id, index) => {
              const item = investigators.find((person) => person.investigator_id === id);
              return <span className={index === turnIndex ? "active" : ""} key={id}>{index + 1}. {item?.profile.name ?? id}</span>;
            })}
          </div> : null}
          <div className="engine-form-grid">
            <label className="field">
              <span>攻击者</span>
              <select disabled={combatActive} value={attackerId} onChange={(event) => setAttackerId(event.target.value)}>
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
              <span>玩家 D100 结果（留空由系统掷）</span>
              <input
                aria-describedby="attack-roll-help"
                max="100"
                min="1"
                type="number"
                value={manualAttackRoll}
                onChange={(event) => setManualAttackRoll(event.target.value)}
              />
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
          <p className="roll-prompt" id="attack-roll-help">
            请掷 D100：需要 ≤ {attackSkillValue || "所选技能"}；困难成功 ≤ {attackSkillValue ? Math.floor(attackSkillValue / 2) : "—"}；极难成功 ≤ {attackSkillValue ? Math.floor(attackSkillValue / 5) : "—"}。命中后再输入武器伤害骰总值。
          </p>
          <div className="engine-actions">
          <button disabled={busy || !attacker || !target || !caseSessionId || (combatActive && turnResolved)} onClick={() => void handleCombat()} type="button">
            结算攻击
          </button>
          {combatActive ? <button className="secondary-button" disabled={busy} onClick={endTurn} type="button">结束当前行动者回合</button> : null}
          </div>
          <p className="section-help">
            系统先写入百分骰攻击记录，再按内置 COC7 武器策略结算伤害与重伤。
          </p>
        </article>

        <article className="engine-panel">
          <h3>追逐</h3>
          <p className="section-help">追逐必须归属一个案件场次，并指定两名不同参与者。追逐者和逃亡者与左侧战斗目标相互独立。</p>
          <div className="engine-form-grid">
            <label className="field">
              <span>追逐者</span>
              <select aria-label="追逐者" value={pursuerId} onChange={(event) => setPursuerId(event.target.value)}>
                <option value="">请选择</option>
                {investigators.map((item) => <option key={item.investigator_id} value={item.investigator_id}>{item.profile.name} · MOV {item.profile.move_rate}</option>)}
              </select>
            </label>
            <label className="field">
              <span>逃亡者</span>
              <select aria-label="逃亡者" value={fleeingId} onChange={(event) => setFleeingId(event.target.value)}>
                <option value="">请选择</option>
                {investigators.map((item) => <option key={item.investigator_id} value={item.investigator_id}>{item.profile.name} · MOV {item.profile.move_rate}</option>)}
              </select>
            </label>
            <label className="field"><span>追者起点</span><input type="number" min="0" value={pursuerPosition} onChange={(event) => setPursuerPosition(Number(event.target.value))} /></label>
            <label className="field"><span>逃者起点</span><input type="number" min="0" value={fleeingPosition} onChange={(event) => setFleeingPosition(Number(event.target.value))} /></label>
            <label className="field"><span>逃脱距离</span><input type="number" min="1" value={escapeDistance} onChange={(event) => setEscapeDistance(Number(event.target.value))} /></label>
            <label className="field"><span>赛道长度</span><input type="number" min="1" value={trackLength} onChange={(event) => setTrackLength(Number(event.target.value))} /></label>
          </div>
          <div className="chase-readiness" aria-label="追逐建立条件" role="region">
            <span className={caseSessionId ? "ready" : ""}>{caseSessionId ? "✓" : "○"} 已选择案件场次</span>
            <span className={investigators.length >= 2 ? "ready" : ""}>{investigators.length >= 2 ? "✓" : "○"} 至少两名调查员</span>
            <span className={pursuer && fleeing && pursuerId !== fleeingId ? "ready" : ""}>{pursuer && fleeing && pursuerId !== fleeingId ? "✓" : "○"} 追逐双方不同</span>
          </div>
          <div className="engine-actions">
            <button disabled={busy} onClick={() => void handleCreateChase()} type="button">
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
        <div className="combat-heading">
          <h3>战斗与追逐日志</h3>
          <button className="secondary-button compact-button" onClick={() => setLogsCollapsed((value) => !value)} type="button">{logsCollapsed ? "+ 展开" : "− 收起"}</button>
        </div>
        {!logsCollapsed ? <div className="operation-list">
          {combatNotes.map((note, index) => <div key={`${index}-${note}`}><strong>{note}</strong></div>)}
          {[...logs]
            .reverse()
            .filter((entry) => (entry.operation_type.startsWith("combat") || entry.operation_type.startsWith("chase")) && (!caseSessionId || entry.case_session_id === caseSessionId))
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
        </div> : <p className="section-help">日志已收起，当前案件场次的记录仍会继续写入。</p>}
      </article>
    </section>
  );
}
