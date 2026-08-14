import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProviderSettings } from "./ProviderSettings";

describe("ProviderSettings", () => {
  const api = {
    createProvider: vi.fn(async () => ({ id: "deepseek", kind: "deepseek" as const, model: "deepseek-chat", version: 1, configured: false })),
    setSessionCredential: vi.fn(async () => ({ id: "deepseek", kind: "deepseek" as const, model: "deepseek-chat", version: 1, configured: true })),
  };
  const props = { api, providers: [], selectedId: "", disabled: false, onProvidersChange: vi.fn(), onSelect: vi.fn() };

  it("打开后聚焦首个对话框控件，对话框外的 Tab 与 Shift+Tab 也强制回到首尾项", async () => {
    const user = userEvent.setup();
    render(<><button type="button">dialog 外</button><ProviderSettings {...props} resetVersion={0} /></>);
    const opener = screen.getByRole("button", { name: "高级设置" });
    await user.click(opener);
    const close = screen.getByRole("button", { name: "关闭" });
    const submit = screen.getByRole("button", { name: "配置会话 Provider" });
    expect(close).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "dialog 外" }));
    await user.keyboard("{Tab}");
    expect(close).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "dialog 外" }));
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(submit).toHaveFocus();
    await user.click(submit);
    await user.keyboard("{Tab}");
    expect(close).toHaveFocus();
    await user.click(close);
    await user.click(opener);
    screen.getByLabelText("类型").focus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(screen.getByRole("button", { name: "关闭" })).toHaveFocus();
  });

  it("会话重置版本变化时清除尚未提交的 API Key", async () => {
    const user = userEvent.setup();
    const view = render(<ProviderSettings {...props} resetVersion={0} />);
    await user.click(screen.getByRole("button", { name: "高级设置" }));
    const key = screen.getByLabelText("API Key");
    await user.type(key, "not-a-secret");
    expect(key).toHaveValue("not-a-secret");
    view.rerender(<ProviderSettings {...props} resetVersion={1} />);
    expect(screen.getByLabelText("API Key")).toHaveValue("");
  });
});
