import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CombatChasePage } from "./CombatChasePage";
import { SanityInjuryPage } from "./SanityInjuryPage";

const campaign = { campaign_id: "campaign-1", title: "雾中来客", ruleset: "coc7e", era: "1920s", enabled_source_pack_ids: [], house_rules: [], version: 1 };
const session = { entity_id: "session-1", campaign_id: "campaign-1", kind: "sessions", title: "第一夜", player_visible_text: "", keeper_truth: "", status: "active", time_label: null, role: null, session_id: null, location_id: null, scene_id: null, person_id: null, clue_id: null, source_clue_id: null, target_clue_id: null, relationship_type: null, discovered: false, revealed: false, sort_order: 0, version: 1, created_at: "2026-01-01", updated_at: "2026-01-01" };
const investigator = (id: string, name: string) => ({ investigator_id: id, campaign_id: "campaign-1", hit_points: 10, magic_points: 10, sanity: 50, mythos: 0, conditions: [], version: 1, profile: { name, player_name: null, occupation: "记者", age: 28, gender: null, residence: null, birthplace: null, era: "1920s", characteristics: { strength: 50, constitution: 60, size: 50, dexterity: 60, appearance: 50, intelligence: 70, power: 50, education: 60 }, luck: 50, move_rate: 8, damage_bonus: "0", build: 0, credit_rating: 20, spending_level: null, cash: null, assets: null, skills: [{ skill_key: "fighting_brawl", display_name: "斗殴", specialization: null, base_value: 25, current_value: 55, improvement_mark: false, source_pack_id: null }, { skill_key: "medicine", display_name: "医学", specialization: null, base_value: 1, current_value: 60, improvement_mark: false, source_pack_id: null }], backstory: { personal_description: [], ideology_and_beliefs: [], significant_people: [], meaningful_locations: [], treasured_possessions: [], traits: [], injuries_and_scars: [], phobias_and_manias: [], mythos_tomes_spells_artifacts: [] } } });
const people = [investigator("inv-1", "林若岚"), investigator("inv-2", "周远")];
const citation = { citation_id: "0d626519-a343-5a71-998c-9b0b56f76232", source_pack_id: "coc7e.core.zh-v1.2.1", filename: "test.pdf", page: 1, section: "test", edition: "7e", module: "core", era: [], checksum: "22f5f56b7a0989cbded695d39c7d5eddddd809cfc9d2c47e4cf4c5d7edea6815" };
const citations = [citation];
const chase = { chase_id: "chase-1", campaign_id: "campaign-1", title: "现场追逐", case_session_id: "session-1", session_key: null, status: "active", round: 1, escape_distance: 10, track_length: 10, version: 1, citation, citations, created_at: "2026-01-01", updated_at: "2026-01-01", participants: [{ investigator_id: "inv-1", role: "pursuer", position: 0, move_rate: 8, actions_remaining: 1 }, { investigator_id: "inv-2", role: "fleeing", position: 2, move_rate: 8, actions_remaining: 1 }] };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function mockFetch(hasSession = true, operations: unknown[] = []): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/campaigns") && !init?.method) return Promise.resolve(json([campaign]));
    if (url.endsWith("/case-state/sessions")) return Promise.resolve(json(hasSession ? [session] : []));
    if (url.endsWith("/investigators")) return Promise.resolve(json(people));
    if (url.endsWith("/rule-operations")) return Promise.resolve(json(operations));
    if (url.endsWith("/rule-engines/weapons")) return Promise.resolve(json([{ weapon_key: "unarmed", name: "徒手", damage_notation: "1D3", maximum_rolled_damage: 3, skill_key: "fighting_brawl", uses_damage_bonus: true, citation, citations }]));
    if (url.endsWith("/chases")) return Promise.resolve(json(init?.method === "POST" ? chase : []));
    if (url.endsWith("/rolls")) return Promise.resolve(json({ roll_id: "roll-1", roll: 20, tens: [2], ones: 0, target: 70, regular_threshold: 70, hard_threshold: 35, extreme_threshold: 14, outcome: "regular", difficulty: "regular", bonus_penalty: 0, passed: true }, 201));
    if (url.endsWith("/sanity-loss")) return Promise.resolve(json({ operation_id: "op-1", operation_type: "sanity_loss", investigator: people[0], target: null, citation, citations, loss: 5, session_sanity_loss: 5, reason: "现场冲击", damage_applied: null, injury_id: null, healed: null, care_type: null, hit: null, weapon_key: null, attack_roll_id: null, created_at: "2026-01-01" }));
    if (url.endsWith("/combat/resolve")) return Promise.resolve(json({ operation_id: "op-2", operation_type: "combat", investigator: people[0], target: people[1], citation, citations, loss: null, session_sanity_loss: null, reason: null, damage_applied: 1, injury_id: null, healed: null, care_type: null, hit: true, weapon_key: "unarmed", attack_roll_id: "roll-1", created_at: "2026-01-01" }));
    return Promise.resolve(json({ detail: "unexpected request" }, 500));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("engine session compatibility", () => {
  it("records an INT roll and sends its id with SAN loss", async () => {
    const fetchMock = mockFetch();
    render(<SanityInjuryPage />);
    await waitFor(() => expect(screen.getByLabelText("案件场次")).toHaveValue("session-1"));
    fireEvent.change(screen.getByLabelText("理智损失"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "记录理智损失" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/sanity-loss"))).toBe(true));
    const rollBody = JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url).endsWith("/rolls"))?.[1]?.body));
    const sanBody = JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url).endsWith("/sanity-loss"))?.[1]?.body));
    expect(rollBody).toMatchObject({ case_session_id: "session-1", skill_key: "intelligence" });
    expect(sanBody).toMatchObject({ case_session_id: "session-1", intelligence_roll_id: "roll-1" });
  });

  it("ties combat roll and resolution to the selected case session", async () => {
    const fetchMock = mockFetch();
    render(<CombatChasePage />);
    await waitFor(() => expect(screen.getByLabelText("案件场次")).toHaveValue("session-1"));
    fireEvent.click(screen.getByRole("button", { name: "结算攻击" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/combat/resolve"))).toBe(true));
    const rollBody = JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url).endsWith("/rolls"))?.[1]?.body));
    const combatBody = JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url).endsWith("/combat/resolve"))?.[1]?.body));
    expect(rollBody).toMatchObject({ case_session_id: "session-1", skill_key: "fighting_brawl", target: 55 });
    expect(combatBody).toMatchObject({ case_session_id: "session-1", attack_roll_id: "roll-1" });
  });

  it("runs a multi-participant DEX turn order and accepts a player's D100", async () => {
    const fetchMock = mockFetch();
    render(<CombatChasePage />);
    await waitFor(() => expect(screen.getByLabelText("案件场次")).toHaveValue("session-1"));
    fireEvent.click(screen.getByRole("button", { name: "开始战斗" }));
    expect(screen.getByText(/第 1 轮 · 当前行动者：林若岚/)).toBeInTheDocument();
    expect(screen.getByLabelText("攻击者")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("玩家 D100 结果（留空由系统掷）"), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "结算攻击" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/combat/resolve"))).toBe(true));
    const rollBody = JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url).endsWith("/rolls"))?.[1]?.body));
    expect(rollBody.dice).toEqual({ units_digit: 2, tens_digits: [4] });
    expect(screen.getByRole("button", { name: "结算攻击" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "结束当前行动者回合" }));
    expect(screen.getByText(/第 1 轮 · 当前行动者：周远/)).toBeInTheDocument();
  });

  it("resets the combat turn table without pretending to roll back persisted damage", async () => {
    mockFetch();
    render(<CombatChasePage />);
    await waitFor(() => expect(screen.getByLabelText("案件场次")).toHaveValue("session-1"));
    fireEvent.click(screen.getByRole("button", { name: "开始战斗" }));
    fireEvent.click(screen.getByRole("button", { name: "重置战斗" }));
    expect(screen.getByText("战斗回合台已重置。已写入的伤害和规则日志不会被撤销。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始战斗" })).toBeEnabled();
  });

  it("explains why SAN cannot be recorded without a case session", async () => {
    mockFetch(false);
    render(<SanityInjuryPage />);
    await waitFor(() => expect(screen.getByLabelText("调查员")).toHaveValue("inv-1"));
    fireEvent.click(screen.getByRole("button", { name: "记录理智损失" }));
    expect(await screen.findByText("请先选择案件场次；规则操作必须归属到场次。"))
      .toBeInTheDocument();
  });

  it("offers every recent injury operation for recovery", async () => {
    mockFetch(true, [
      { operation_id: "op-old", campaign_id: "campaign-1", subject_id: "inv-1", case_session_id: "session-1", session_key: null, operation_type: "injury", input_data: {}, output_data: { injury_id: "injury-old" }, citation, citations, created_at: "2026-01-01" },
      { operation_id: "op-new", campaign_id: "campaign-1", subject_id: "inv-1", case_session_id: "session-1", session_key: null, operation_type: "injury", input_data: {}, output_data: { injury_id: "injury-new" }, citation, citations, created_at: "2026-01-02" },
    ]);
    render(<SanityInjuryPage />);
    await waitFor(() => expect(screen.getByLabelText("要恢复的伤势")).toHaveValue("injury-new"));
    expect(screen.getByLabelText("要恢复的伤势")).toContainHTML('value="injury-old"');
    expect(screen.getByLabelText("要恢复的伤势")).toContainHTML('value="injury-new"');
  });

  it("sends selected chase positions and lets the user choose its participant action", async () => {
    const fetchMock = mockFetch();
    render(<CombatChasePage />);
    await waitFor(() => expect(screen.getByLabelText("案件场次")).toHaveValue("session-1"));
    fireEvent.change(screen.getByLabelText("追者起点"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("逃者起点"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "建立追逐" }));
    await waitFor(() => expect(screen.getByLabelText("选择追逐")).toHaveValue("chase-1"));
    const body = JSON.parse(String(fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/chases") && init?.method === "POST")?.[1]?.body));
    expect(body).toMatchObject({ case_session_id: "session-1", participants: [{ investigator_id: "inv-1", role: "pursuer", position: 1 }, { investigator_id: "inv-2", role: "fleeing", position: 4 }] });
    expect(screen.getByLabelText("行动者")).toHaveValue("inv-1");
  });

  it("keeps chase creation actionable and explains missing prerequisites", async () => {
    mockFetch(false);
    render(<CombatChasePage />);
    await waitFor(() => expect(screen.getByLabelText("追逐者")).toHaveValue("inv-1"));
    expect(screen.getByRole("button", { name: "建立追逐" })).toBeEnabled();
    expect(screen.getByRole("region", { name: "追逐建立条件" })).toHaveTextContent("○ 已选择案件场次");
    fireEvent.click(screen.getByRole("button", { name: "建立追逐" }));
    expect(await screen.findByText("建立追逐必须选择案件场次。")).toBeInTheDocument();
  });
});
