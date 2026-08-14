import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IntentCardView } from "./IntentCardView";

describe("IntentCardView", () => {
  it("将意图、行动、预期、实际、证据和状态对齐展示", () => {
    render(<IntentCardView card={{ id: "card-1", task_id: "task-1", kind: "verification_failure", intent: "验证修复", action: "运行 make test", expected_result: "所有测试通过", actual_result: "1 项失败", evidence_sequences: [7, 9], status: "needs_correction", source_event_sequence: 9, learning_card_id: null }} question="" answer="" correction="" busy={false} branchExists={false} onQuestion={vi.fn()} onAsk={vi.fn()} onCorrection={vi.fn()} onCreateCorrection={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "验证修复" })).toBeVisible();
    expect(screen.getByText("行动")).toBeVisible();
    expect(screen.getByText("运行 make test")).toBeVisible();
    expect(screen.getByText("预期结果")).toBeVisible();
    expect(screen.getByText("所有测试通过")).toBeVisible();
    expect(screen.getByText("实际结果")).toBeVisible();
    expect(screen.getByText("1 项失败")).toBeVisible();
    expect(screen.getByText("证据序号")).toBeVisible();
    expect(screen.getByText("7, 9")).toBeVisible();
    expect(screen.getByText("状态")).toBeVisible();
    expect(screen.getByText("needs_correction")).toBeVisible();
  });
});
