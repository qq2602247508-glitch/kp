import type {
  Campaign,
  CampaignCreate,
  CaseEntityKind,
  CaseEntry,
  CaseEntryDraft,
  PlayerCaseEntry,
  Investigator,
  InvestigatorCondition,
  InvestigatorProfile,
  InvestigatorUpdate,
  Chase,
  ChaseParticipant,
  EngineOperation,
  RuleOperationLog,
  StateAuditLog,
  WeaponPolicy,
  RollRequest,
  RollResult,
  RuleAnswerResponse,
  RuleFilters,
  RuleSearchResponse,
  AIKPResponse,
  AIProposal,
  BackupResult,
  CampaignExport,
  CampaignSourcePacks,
  DeliveryReadiness,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");

type InvestigatorWire = InvestigatorProfile & {
  investigator_id: string;
  campaign_id: string;
  hit_points: number;
  magic_points: number;
  sanity: number;
  mythos: number;
  conditions: InvestigatorCondition[];
  version: number;
};

type EngineOperationWire = Omit<EngineOperation, "investigator" | "target"> & {
  investigator: InvestigatorWire | Investigator;
  target: InvestigatorWire | Investigator | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function describeErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String(item.msg);
        }
        return "";
      })
      .filter(Boolean);
    if (messages.length > 0) return messages.join("；");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`.trim();
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = describeErrorDetail(body.detail, detail);
    } catch {
      // The status text remains the most useful available message.
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function listCampaigns(signal?: AbortSignal): Promise<Campaign[]> {
  return request<Campaign[]>("/campaigns", { signal });
}

export function createCampaign(payload: CampaignCreate): Promise<Campaign> {
  return request<Campaign>("/campaigns", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listCaseEntries(
  campaignId: string,
  kind: CaseEntityKind,
  signal?: AbortSignal,
): Promise<CaseEntry[]> {
  return request<CaseEntry[]>(
    `/campaigns/${campaignId}/case-state/${kind}`,
    { signal },
  );
}

export function getPlayerCaseEntry(
  campaignId: string,
  kind: CaseEntityKind,
  entityId: string,
  signal?: AbortSignal,
): Promise<PlayerCaseEntry> {
  return request<PlayerCaseEntry>(
    `/campaigns/${campaignId}/case-state/${kind}/${entityId}/player-view`,
    { signal },
  );
}

export function createCaseEntry(
  campaignId: string,
  kind: CaseEntityKind,
  payload: CaseEntryDraft,
): Promise<CaseEntry> {
  return request<CaseEntry>(`/campaigns/${campaignId}/case-state/${kind}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCaseEntry(
  campaignId: string,
  kind: CaseEntityKind,
  entityId: string,
  payload: CaseEntryDraft & { expected_version: number },
): Promise<CaseEntry> {
  return request<CaseEntry>(
    `/campaigns/${campaignId}/case-state/${kind}/${entityId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteCaseEntry(
  campaignId: string,
  kind: CaseEntityKind,
  entityId: string,
  expectedVersion: number,
): Promise<void> {
  return request<void>(
    `/campaigns/${campaignId}/case-state/${kind}/${entityId}?expected_version=${expectedVersion}`,
    { method: "DELETE" },
  );
}

export function listInvestigators(
  campaignId: string,
  signal?: AbortSignal,
): Promise<Investigator[]> {
  return request<Array<InvestigatorWire | Investigator>>(
    `/campaigns/${campaignId}/investigators`,
    { signal },
  ).then((items) => items.map(normalizeInvestigator));
}

export function createInvestigator(
  campaignId: string,
  payload: InvestigatorProfile,
): Promise<Investigator> {
  return request<InvestigatorWire | Investigator>(
    `/campaigns/${campaignId}/investigators`,
    {
    method: "POST",
    body: JSON.stringify(payload),
    },
  ).then(normalizeInvestigator);
}

export function updateInvestigator(
  campaignId: string,
  investigatorId: string,
  payload: InvestigatorUpdate,
): Promise<Investigator> {
  return request<InvestigatorWire | Investigator>(
    `/campaigns/${campaignId}/investigators/${investigatorId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  ).then(normalizeInvestigator);
}

export function resolveRoll(payload: RollRequest): Promise<RollResult> {
  return request<RollResult>("/rolls", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function searchRules(
  query: string,
  filters: RuleFilters,
  signal?: AbortSignal,
): Promise<RuleSearchResponse> {
  const params = ruleQueryParams(query, filters);
  return request<RuleSearchResponse>(`/rules/search?${params.toString()}`, {
    signal,
  });
}

export function answerRules(
  question: string,
  filters: RuleFilters,
  signal?: AbortSignal,
): Promise<RuleAnswerResponse> {
  return request<RuleAnswerResponse>("/rules/answer", {
    method: "POST",
    body: JSON.stringify({
      question,
      source_pack_ids: cleanFilter(filters.sourcePack),
      editions: cleanFilter(filters.edition),
      modules: cleanFilter(filters.module),
      eras: cleanFilter(filters.era),
      limit: 8,
    }),
    signal,
  });
}

export function applySanityLoss(
  campaignId: string,
  investigatorId: string,
  payload: {
    expected_version: number;
    loss: number;
    reason: string;
    session_key: string;
    case_session_id: string;
    intelligence_roll_id?: string;
  },
): Promise<EngineOperation> {
  return request<EngineOperationWire>(
    `/campaigns/${campaignId}/investigators/${investigatorId}/sanity-loss`,
    { method: "POST", body: JSON.stringify(payload) },
  ).then(normalizeEngineOperation);
}

export function applyInjury(
  campaignId: string,
  investigatorId: string,
  payload: {
    expected_version: number;
    damage: number;
    reason: string;
    session_key?: string;
    case_session_id: string;
  },
): Promise<EngineOperation> {
  return request<EngineOperationWire>(
    `/campaigns/${campaignId}/investigators/${investigatorId}/injury`,
    { method: "POST", body: JSON.stringify(payload) },
  ).then(normalizeEngineOperation);
}

export function applyRecovery(
  campaignId: string,
  investigatorId: string,
  payload: {
    expected_version: number;
    care_type: "first_aid" | "medicine" | "natural";
    injury_id: string;
    healing_roll?: number;
    medicine_roll_id?: string;
    first_aid_roll_id?: string;
    constitution_roll_id?: string;
    period_key?: string;
    session_key?: string;
    case_session_id: string;
  },
): Promise<EngineOperation> {
  return request<EngineOperationWire>(
    `/campaigns/${campaignId}/investigators/${investigatorId}/recovery`,
    { method: "POST", body: JSON.stringify(payload) },
  ).then(normalizeEngineOperation);
}

export function applyDyingCheck(campaignId: string, investigatorId: string, payload: { expected_version: number; constitution_roll_id: string; period_key: string; session_key?: string; case_session_id: string }): Promise<EngineOperation> {
  return request<EngineOperationWire>(`/campaigns/${campaignId}/investigators/${investigatorId}/dying-check`, { method: "POST", body: JSON.stringify(payload) }).then(normalizeEngineOperation);
}

export function applyInsanityTransition(campaignId: string, investigatorId: string, payload: { expected_version: number; transition: "bout_started" | "bout_ended" | "recovered"; period_key?: string; evidence?: string; treatment_roll_id?: string; session_key?: string; case_session_id: string }): Promise<EngineOperation> {
  return request<EngineOperationWire>(`/campaigns/${campaignId}/investigators/${investigatorId}/insanity-transition`, { method: "POST", body: JSON.stringify(payload) }).then(normalizeEngineOperation);
}

export function listRuleOperations(
  campaignId: string,
  signal?: AbortSignal,
): Promise<RuleOperationLog[]> {
  return request<RuleOperationLog[]>(
    `/campaigns/${campaignId}/rule-operations`,
    { signal },
  );
}

export function listStateAudits(
  campaignId: string,
  signal?: AbortSignal,
): Promise<StateAuditLog[]> {
  return request<StateAuditLog[]>(`/campaigns/${campaignId}/audits`, {
    signal,
  });
}

export function listWeapons(signal?: AbortSignal): Promise<WeaponPolicy[]> {
  return request<WeaponPolicy[]>("/rule-engines/weapons", { signal });
}

export function resolveCombat(
  campaignId: string,
  payload: {
    attacker_id: string;
    target_id: string;
    target_expected_version: number;
    attack_roll_id: string;
    weapon_key: string;
    rolled_damage: number;
    session_key?: string;
    case_session_id: string;
  },
): Promise<EngineOperation> {
  return request<EngineOperationWire>(`/campaigns/${campaignId}/combat/resolve`, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(normalizeEngineOperation);
}

export function listChases(
  campaignId: string,
  signal?: AbortSignal,
): Promise<Chase[]> {
  return request<Chase[]>(`/campaigns/${campaignId}/chases`, { signal });
}

export function createChase(
  campaignId: string,
  payload: {
    title: string;
    session_key?: string;
    case_session_id: string;
    participants: Pick<ChaseParticipant, "investigator_id" | "role" | "position">[];
    escape_distance?: number;
    track_length?: number;
  },
): Promise<Chase> {
  return request<Chase>(`/campaigns/${campaignId}/chases`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function advanceChase(
  campaignId: string,
  chaseId: string,
  payload: {
    expected_version: number;
    action: { investigator_id: string; action: "move" | "hazard"; roll_id?: string; skill_key?: string };
  },
): Promise<Chase> {
  return request<Chase>(
    `/campaigns/${campaignId}/chases/${chaseId}/advance`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function askAIKP(
  campaignId: string,
  payload: {
    question: string;
    mode: "answer" | "private_hint" | "scenario_draft";
  },
): Promise<AIKPResponse> {
  return request<AIKPResponse>(`/campaigns/${campaignId}/ai-kp/ask`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listAIProposals(
  campaignId: string,
  signal?: AbortSignal,
): Promise<AIProposal[]> {
  return request<AIProposal[]>(
    `/campaigns/${campaignId}/ai-kp/proposals`,
    { signal },
  );
}

export function decideAIProposal(
  campaignId: string,
  proposalId: string,
  payload: {
    expected_version: number;
    decision: "confirm" | "reject";
    reason?: string;
  },
): Promise<AIProposal> {
  return request<AIProposal>(
    `/campaigns/${campaignId}/ai-kp/proposals/${proposalId}/decision`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function getDeliveryReadiness(signal?: AbortSignal): Promise<DeliveryReadiness> {
  return request<DeliveryReadiness>("/delivery/readiness", { signal });
}

export function getCampaignSourcePacks(
  campaignId: string,
  signal?: AbortSignal,
): Promise<CampaignSourcePacks> {
  return request<CampaignSourcePacks>(
    `/campaigns/${campaignId}/source-packs`,
    { signal },
  );
}

export function updateCampaignSourcePacks(
  campaignId: string,
  expectedVersion: number,
  enabledSourcePackIds: string[],
): Promise<CampaignSourcePacks> {
  return request<CampaignSourcePacks>(
    `/campaigns/${campaignId}/source-packs`,
    {
      method: "PUT",
      body: JSON.stringify({
        expected_version: expectedVersion,
        enabled_source_pack_ids: enabledSourcePackIds,
      }),
    },
  );
}

export function exportCampaign(campaignId: string): Promise<CampaignExport> {
  return request<CampaignExport>(`/campaigns/${campaignId}/export`);
}

export function importCampaign(bundle: CampaignExport): Promise<{ campaign_id: string; status: string }> {
  return request<{ campaign_id: string; status: string }>("/imports/campaign", {
    method: "POST",
    body: JSON.stringify(bundle),
  });
}

export function createBackup(destination?: string): Promise<BackupResult> {
  return request<BackupResult>("/delivery/backups", {
    method: "POST",
    body: JSON.stringify({ destination: destination || null }),
  });
}

export function verifyBackup(path: string): Promise<{
  valid: boolean;
  mismatches: string[];
  restore_performed: false;
}> {
  return request("/delivery/backups/verify", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

function ruleQueryParams(query: string, filters: RuleFilters): URLSearchParams {
  const params = new URLSearchParams({ q: query, limit: "8" });
  appendFilters(params, "source_pack", filters.sourcePack);
  appendFilters(params, "edition", filters.edition);
  appendFilters(params, "module", filters.module);
  appendFilters(params, "era", filters.era);
  return params;
}

function appendFilters(
  params: URLSearchParams,
  key: string,
  value: string | undefined,
): void {
  for (const item of cleanFilter(value)) {
    params.append(key, item);
  }
}

function cleanFilter(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeInvestigator(value: InvestigatorWire | Investigator): Investigator {
  if ("profile" in value) {
    return value;
  }
  const {
    investigator_id,
    campaign_id,
    hit_points,
    magic_points,
    sanity,
    mythos,
    conditions,
    version,
    ...profile
  } = value;
  return {
    investigator_id,
    campaign_id,
    hit_points,
    magic_points,
    sanity,
    mythos,
    conditions,
    version,
    profile,
  };
}

function normalizeEngineOperation(value: EngineOperationWire): EngineOperation {
  return {
    ...value,
    investigator: normalizeInvestigator(value.investigator),
    target: value.target ? normalizeInvestigator(value.target) : null,
  };
}
