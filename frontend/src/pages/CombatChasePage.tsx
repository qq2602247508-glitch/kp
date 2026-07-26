import { useEffect, useMemo, useState, type ReactElement } from "react";

import {
  ApiError,
  advanceChase,
  createChase,
  listCampaigns,
  listChases,
  listInvestigators,
  listRuleOperations,
  listWeapons,
  resolveCombat,
  resolveRoll,
} from "../api/client";
import type {
  Campaign,
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

export function CombatChasePage(): ReactElement {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [investigators, setInvestigators] = useState<Investigator[]>([]);
  const [attackerId, setAttackerId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [weapons, setWeapons] = useState<WeaponPolicy[]>([]);
  const [weaponKey, setWeaponKey] = useState("unarmed");
  const [damage, setDamage] = useState(1);
  const [chases, setChases] = useState<Chase[]>([]);
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
  const activeChase = chases[0];

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
      return;
    }
    const controller = new AbortController();
    Promise.all([
      listInvestigators(campaignId, controller.signal),
      listChases(campaignId, controller.signal),
      listRuleOperations(campaignId, controller.signal),
    ])
      .then(([people, chaseItems, operationItems]) => {
        setInvestigators(people);
        setAttackerId((current) => current || people[0]?.investigator_id || "");
        setTargetId((current) => current || people[1]?.investigator_id || "");
        setChases(chaseItems);
        setLogs(operationItems);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailure(errorMessage(error));
        }
      });
    return () => controller.abort();
  }, [campaignId]);

  async function handleCombat(): Promise<void> {
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

  async function handleCreateChase(): Promise<void> {
    if (!attacker || !target || attacker.investigator_id === target.investigator_id) {
      setFailure("建立追逐需要两名不同的参与者。");
      return;
    }
    setBusy(true);
    try {
      const chase = await createChase(campaignId, {
        title: "现场追逐",
        participants: [
          { investigator_id: attacker.investigator_id, role: "pursuer", position: 0 },
          { investigator_id: target.investigator_id, role: "fleeing", position: 2 },
        ],
      });
      setChases((items) => [chase, ...items]);
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
    if (!activeChase) return;
    setBusy(true);
    try {
      const chase = await advanceChase(campaignId, activeChase.chase_id, {
        expected_version: activeChase.version,
        moves: activeChase.participants.map((participant) => ({
          investigator_id: participant.investigator_id,
          move_units: 1,
        })),
      });
      setChases((items) =>
        items.map((item) => (item.chase_id === chase.chase_id ? chase : item)),
      );
      setLogs(await listRuleOperations(campaignId));
      setNotice("追逐推进了一轮。");
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
          <select value={campaignId} onChange={(event) => setCampaignId(event.target.value)}>
            <option value="">请选择</option>
            {campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.title}
              </option>
            ))}
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
          <button disabled={busy || !attacker || !target} onClick={() => void handleCombat()} type="button">
            结算攻击
          </button>
          <p className="section-help">
            系统先写入百分骰攻击记录，再按内置 COC7 武器策略结算伤害与重伤。
          </p>
        </article>

        <article className="engine-panel">
          <h3>追逐</h3>
          <div className="engine-actions">
            <button disabled={busy || investigators.length < 2} onClick={() => void handleCreateChase()} type="button">
              建立追逐
            </button>
            <button
              className="secondary-button"
              disabled={busy || !activeChase}
              onClick={() => void handleAdvance()}
              type="button"
            >
              推进一轮
            </button>
          </div>
          {activeChase ? (
            <div className="chase-track">
              <strong>{activeChase.title}</strong>
              {activeChase.participants.map((participant) => (
                <span key={participant.investigator_id}>
                  {investigators.find(
                    (item) => item.investigator_id === participant.investigator_id,
                  )?.profile.name ?? participant.investigator_id}
                  ：位置 {participant.position}（{participant.role}）
                </span>
              ))}
              <small>
                {activeChase.citation.filename} · 第 {activeChase.citation.page} 页 ·{" "}
                {activeChase.citation.section}
              </small>
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
                <span>
                  {entry.citation.filename} · 第 {entry.citation.page} 页 ·{" "}
                  {entry.citation.section}
                </span>
              </div>
            ))}
        </div>
      </article>
    </section>
  );
}
