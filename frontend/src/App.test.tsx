import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("COC KP application shell", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/campaigns")) {
          return {
            ok: true,
            json: async () => [
              { campaign_id: "campaign-1", title: "雾港失踪案", era: "1920s" },
              { campaign_id: "campaign-2", title: "白河旧宅", era: "gaslight" },
            ],
          };
        }
        if (url.endsWith("/delivery/readiness")) {
          return {
            ok: true,
            json: async () => ({
              ready: true,
              database: { status: "ready" },
              sources: { status: "ready", ready_packs: 3, failed_packs: 0 },
              vector_index: { status: "ready", chunk_count: 42 },
              models: {
                provider: "ollama",
                provider_status: "ready",
                embedding: { name: "bge-m3:latest", status: "ready", installed: true, download_attempted: false },
                completion: { name: "qwen3:30b-instruct", status: "ready", installed: true, download_attempted: false },
              },
            }),
          };
        }
        return { ok: true, json: async () => [] };
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows readiness and dashboard counts from the real API", async () => {
    render(<App />);

    expect(await screen.findByText("本地服务已就绪 · 8010")).toBeInTheDocument();
    expect(await screen.findByText("3 个资料包，42 个可检索片段。")).toBeInTheDocument();
    expect(screen.queryByText(/未索引|待连接|演示数字/)).not.toBeInTheDocument();
  });

  it("changes the global campaign and persists it", async () => {
    render(<App />);
    const picker = await screen.findByRole("combobox", { name: "全局当前案件" });

    expect(picker).toHaveValue("campaign-1");
    expect(window.localStorage.getItem("local-coc-kp-assistant:selected-campaign")).toBe("campaign-1");
    expect(screen.getByText("雾港失踪案：守秘档案已展开。")).toBeInTheDocument();
  });

  it("preserves a stored campaign while navigating between workspaces", async () => {
    window.localStorage.setItem(
      "local-coc-kp-assistant:selected-campaign",
      "campaign-2",
    );
    render(<App />);

    const globalPicker = await screen.findByRole("combobox", {
      name: "全局当前案件",
    });
    expect(globalPicker).toHaveValue("campaign-2");

    fireEvent.click(screen.getByRole("button", { name: /调查员/ }));
    expect(await screen.findByLabelText("当前调查")).toHaveValue("campaign-2");
    expect(globalPicker).toHaveValue("campaign-2");

    fireEvent.click(screen.getByRole("button", { name: /审计日志/ }));
    expect(await screen.findByRole("heading", { name: "状态与规则审计" })).toBeInTheDocument();
    expect(globalPicker).toHaveValue("campaign-2");
  });

  it("starts on the keeper dashboard", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "守秘人仪表板" }),
    ).toBeInTheDocument();
    expect(screen.getByText("AI 的变更必须经 KP 确认")).toBeInTheDocument();
  });

  it("opens the native investigator character sheet", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /调查员/ }));

    expect(
      await screen.findByRole("heading", { name: "COC7 调查员角色卡" }),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText("当前调查员")).toBeInTheDocument();
  });

  it("opens the grounded COC7 rules workspace", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /COC7 规则库/ }));

    expect(
      screen.getByRole("heading", { name: "有据可查的规则检索" }),
    ).toBeInTheDocument();
  });

  it("opens a usable clue-network case workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /线索网络/ }));

    expect(
      await screen.findByRole("heading", { name: "案件线索网络" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建线索" })).toBeInTheDocument();
    expect(screen.getByText("玩家可见信息")).toBeInTheDocument();
    expect(screen.getByText("KP 真相")).toBeInTheDocument();
  });

  it("opens usable sanity and encounter engines instead of placeholders", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /理智与疯狂/ }));
    expect(
      await screen.findByRole("heading", { name: "理智、疯狂与伤势" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "记录理智损失" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /战斗与追逐/ }));
    expect(
      await screen.findByRole("heading", { name: "战斗与追逐记录台" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "结算攻击" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "建立追逐" })).toBeInTheDocument();
  });

  it("opens real AI KP and proposal workspaces with advisory-only controls", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /AI KP 助手/ }));
    expect(
      await screen.findByRole("heading", { name: "AI KP 私密工作台" }),
    ).toBeInTheDocument();
    expect(screen.getByText("模型建议尚未生效")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成建议" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /提案中心/ }));
    expect(
      await screen.findByRole("heading", { name: "待确认提案中心" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/确认前不会写入案件资料/)).toBeInTheDocument();
  });

  it("opens the state and rule audit workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /审计日志/ }));

    expect(
      await screen.findByRole("heading", { name: "状态与规则审计" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "审计类型" })).toBeInTheDocument();
  });

  it("opens the real settings and delivery workspace", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /设置与备份/ }));

    expect(
      screen.getByRole("heading", { name: "设置、资料与可恢复交付" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建一致性备份" })).toBeInTheDocument();
  });
});
