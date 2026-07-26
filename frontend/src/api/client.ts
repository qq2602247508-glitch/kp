import type {
  Campaign,
  CampaignCreate,
  CaseEntityKind,
  CaseEntry,
  CaseEntryDraft,
  Investigator,
  InvestigatorCondition,
  InvestigatorProfile,
  InvestigatorUpdate,
  RollRequest,
  RollResult,
  RuleAnswerResponse,
  RuleFilters,
  RuleSearchResponse,
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

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
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
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // The status text remains the most useful available message.
    }
    throw new ApiError(detail, response.status);
  }

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
  return fetch(
    `${API_BASE}/campaigns/${campaignId}/case-state/${kind}/${entityId}?expected_version=${expectedVersion}`,
    { method: "DELETE", headers: { Accept: "application/json" } },
  ).then((response) => {
    if (!response.ok) {
      throw new ApiError(`${response.status} ${response.statusText}`.trim(), response.status);
    }
  });
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
