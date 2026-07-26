import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsDeliveryPage } from "./SettingsDeliveryPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("settings and delivery workspace", () => {
  it("shows real readiness and strict per-campaign source packs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/delivery/readiness")) {
          return {
            ok: true,
            json: async () => ({
              product: "local-coc-kp-assistant",
              ruleset: "coc7e",
              ready: true,
              database: { status: "ready" },
              sources: { status: "ready", ready_packs: 20, failed_packs: 0 },
              vector_index: { status: "ready", chunk_count: 5484 },
              models: {
                provider: "ollama",
                provider_status: "ready",
                embedding: {
                  name: "bge-m3:latest",
                  status: "ready",
                  installed: true,
                  download_attempted: false,
                },
                completion: {
                  name: "qwen3:30b-instruct",
                  status: "ready",
                  installed: true,
                  download_attempted: false,
                },
              },
            }),
          };
        }
        if (url.endsWith("/campaigns")) {
          return {
            ok: true,
            json: async () => [
              {
                campaign_id: "campaign-1",
                title: "雾港档案",
                ruleset: "coc7e",
                era: "1920s",
                enabled_source_pack_ids: [],
                house_rules: [],
                version: 1,
              },
            ],
          };
        }
        return {
          ok: true,
          json: async () => ({
            campaign_id: "campaign-1",
            campaign_version: 1,
            enabled_source_pack_ids: ["coc7e.core.zh-v1.2.1"],
            packs: [
              {
                pack_id: "coc7e.core.zh-v1.2.1",
                title: "COC7th 核心规则书",
                version: "1.2.1",
                edition: "7e",
                kind: "core",
                default_enabled: true,
                eras: [],
                compatible: true,
                required_default: true,
                enabled: true,
              },
            ],
          }),
        };
      }),
    );

    render(<SettingsDeliveryPage />);

    expect(await screen.findByText("全部就绪")).toBeInTheDocument();
    expect(screen.getByText("5484 个规则片段")).toBeInTheDocument();
    expect(screen.getByText("bge-m3:latest")).toBeInTheDocument();
    expect(screen.getByText("qwen3:30b-instruct")).toBeInTheDocument();
    expect(await screen.findByText("COC7th 核心规则书")).toBeInTheDocument();
    expect(screen.getByText(/不会自动下载模型或浏览器/)).toBeInTheDocument();
    expect(screen.getByText(/同 ID 战役不会被覆盖/)).toBeInTheDocument();
  });
});
