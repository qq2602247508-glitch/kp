import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CaseEntityKind, CaseEntry } from "../api/types";
import { CaseWorkspacePage } from "./CaseWorkspacePage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function entry(
  kind: CaseEntityKind,
  entityId: string,
  title: string,
  overrides: Partial<CaseEntry> = {},
): CaseEntry {
  return {
    entity_id: entityId,
    campaign_id: "campaign-1",
    kind,
    title,
    player_visible_text: `${title}的公开信息`,
    keeper_truth: `${title}的秘密`,
    status: "active",
    time_label: null,
    role: null,
    session_id: null,
    location_id: null,
    scene_id: null,
    person_id: null,
    clue_id: null,
    source_clue_id: null,
    target_clue_id: null,
    relationship_type: null,
    discovered: false,
    revealed: false,
    sort_order: 0,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const caseEntries: Record<CaseEntityKind, CaseEntry[]> = {
  sessions: [entry("sessions", "session-1", "第一夜")],
  scenes: [
    entry("scenes", "scene-1", "旧档案馆", {
      session_id: "session-1",
      location_id: "location-1",
    }),
  ],
  people: [entry("people", "person-1", "林馆长")],
  locations: [entry("locations", "location-1", "档案馆")],
  clues: [
    entry("clues", "clue-1", "银色钥匙", {
      scene_id: "scene-1",
      person_id: "person-1",
      location_id: "location-1",
    }),
    entry("clues", "clue-2", "盐渍手稿"),
  ],
  relationships: [
    entry("relationships", "relationship-1", "钥匙指向手稿", {
      source_clue_id: "clue-1",
      target_clue_id: "clue-2",
      relationship_type: "开启",
    }),
  ],
  handouts: [],
  "timeline-events": [],
};

function installCaseApi(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/campaigns")) {
      return Promise.resolve(
        jsonResponse([
          {
            campaign_id: "campaign-1",
            title: "雾中来客",
            ruleset: "coc7e",
            era: "1920s",
            enabled_source_pack_ids: [],
            house_rules: [],
            version: 1,
          },
        ]),
      );
    }
    if (url.endsWith("/player-view")) {
      return Promise.resolve(
        jsonResponse({
          entity_id: "clue-1",
          campaign_id: "campaign-1",
          kind: "clues",
          title: "银色钥匙",
          player_visible_text: "钥匙刻着陌生纹章",
          status: "active",
          time_label: null,
          role: null,
          discovered: true,
          revealed: false,
        }),
      );
    }
    const match = url.match(/case-state\/([^/]+)$/);
    if (match) {
      return Promise.resolve(
        jsonResponse(caseEntries[match[1] as CaseEntityKind]),
      );
    }
    return Promise.resolve(jsonResponse({ detail: "unexpected request" }, 500));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CaseWorkspacePage", () => {
  it("shows the backend error detail instead of a generic failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "案件数据库正在维护" }, 503),
      ),
    );

    render(<CaseWorkspacePage initialKind="clues" />);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "案件数据库正在维护",
    );
  });

  it("loads the complete case graph and uses titled selects for relationships", async () => {
    const fetchMock = installCaseApi();
    render(<CaseWorkspacePage initialKind="clues" />);

    fireEvent.click(await screen.findByRole("button", { name: "线索关联" }));

    const source = await screen.findByLabelText("起点线索");
    const target = screen.getByLabelText("终点线索");
    expect(within(source).getByRole("option", { name: "银色钥匙" })).toHaveValue(
      "clue-1",
    );
    expect(within(target).getByRole("option", { name: "盐渍手稿" })).toHaveValue(
      "clue-2",
    );
    await waitFor(() => {
      const listCalls = fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("/case-state/"),
      );
      expect(listCalls).toHaveLength(8);
    });
  });

  it("keeps scene and clue reference caches available across kind changes", async () => {
    installCaseApi();
    render(<CaseWorkspacePage initialKind="scenes" />);

    const sessionSelect = await screen.findByLabelText("所属团次");
    await waitFor(() =>
      expect(
        within(sessionSelect).getByRole("option", { name: "第一夜" }),
      ).toHaveValue("session-1"),
    );
    expect(
      within(screen.getByLabelText("发生地点")).getByRole("option", {
        name: "档案馆",
      }),
    ).toHaveValue("location-1");

    fireEvent.click(screen.getByRole("button", { name: "线索" }));

    expect(
      within(await screen.findByLabelText("所属场景")).getByRole("option", {
        name: "旧档案馆",
      }),
    ).toHaveValue("scene-1");
    expect(
      within(screen.getByLabelText("相关人物")).getByRole("option", {
        name: "林馆长",
      }),
    ).toHaveValue("person-1");
    expect(
      within(screen.getByLabelText("相关地点")).getByRole("option", {
        name: "档案馆",
      }),
    ).toHaveValue("location-1");
  });

  it("renders the player-view API projection without leaking keeper truth", async () => {
    installCaseApi();
    render(<CaseWorkspacePage initialKind="clues" />);

    fireEvent.click(await screen.findByRole("button", { name: /银色钥匙/ }));

    const preview = await screen.findByRole("region", { name: "玩家视图预览" });
    expect(within(preview).getByText("钥匙刻着陌生纹章")).toBeInTheDocument();
    expect(within(preview).queryByText("银色钥匙的秘密")).not.toBeInTheDocument();
    expect(within(preview).queryByText(/KP 真相/)).not.toBeInTheDocument();
  });
});
