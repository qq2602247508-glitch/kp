import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("COC KP application shell", () => {
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
    expect(await screen.findByText("先建立一场调查")).toBeInTheDocument();
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
});
