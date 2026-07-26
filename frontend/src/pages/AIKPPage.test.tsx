import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AIKPPage } from "./AIKPPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AI KP proposal center", () => {
  it("marks expired proposals and disables decisions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/campaigns")) {
          return {
            ok: true,
            json: async () => [
              {
                campaign_id: "campaign-1",
                title: "雾港失踪案",
                ruleset: "coc7e",
                era: "1920s",
                custom_era_label: null,
                in_world_date: null,
                starting_location: null,
                enabled_source_pack_ids: [],
                house_rules: [],
                keeper_notes: null,
                version: 1,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
              },
            ],
          };
        }
        return {
          ok: true,
          json: async () => [
            {
              proposal_id: "proposal-1",
              campaign_id: "campaign-1",
              proposal_type: "case_state_create",
              case_kind: "scenes",
              target_entity_id: null,
              campaign_version: 1,
              target_version: null,
              payload: { title: "封闭仓库" },
              diff: { title: { before: null, after: "封闭仓库" } },
              evidence: [],
              citation_ids: [],
              model_name: "qwen3:30b-instruct",
              model_metadata: {},
              status: "pending",
              version: 1,
              rejection_reason: null,
              applied_entity_id: null,
              created_at: "2026-01-01T00:00:00Z",
              expires_at: "2026-01-01T01:00:00Z",
              is_expired: true,
              resolved_at: null,
            },
          ],
        };
      }),
    );

    render(<AIKPPage initialView="proposals" />);

    expect(await screen.findByText("已过期")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "确认并写入" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "拒绝" })).not.toBeInTheDocument();
  });
});
