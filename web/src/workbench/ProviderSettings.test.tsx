import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProviderSettings } from "./ProviderSettings";

describe("ProviderSettings", () => {
  it("打开后聚焦首个对话框控件，Tab 与 Shift+Tab 均留在抽屉内", async () => {
    const user = userEvent.setup();
    render(<ProviderSettings api={{}} providers={[]} selectedId="" disabled={false} resetVersion={0} onProvidersChange={vi.fn()} onSelect={vi.fn()} />);
    const opener = screen.getByRole("button", { name: "高级设置" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Provider 高级设置" });
    const close = screen.getByRole("button", { name: "关闭" });
    expect(close).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(close).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(close).toHaveFocus();
    expect(dialog).toBeVisible();
  });
});
