import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type * as ApiClientModule from "../src/api/client";

import { SettingsPage } from "../src/pages/settings/SettingsPage";

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClientModule>();
  return {
    ...actual,
    apiClient: {
      getSettings: vi.fn(),
      updateSettings: vi.fn(),
    },
  };
});

import { apiClient } from "../src/api/client";

describe("SettingsPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("keeps stored Telegram credentials when their replacement fields are blank", async () => {
    vi.mocked(apiClient.getSettings).mockResolvedValue({
      telegram_enabled: true,
      password_configured: true,
      managed_in_gui: true,
    });
    vi.mocked(apiClient.updateSettings).mockResolvedValue({
      telegram_enabled: true,
      password_configured: true,
      managed_in_gui: true,
    });

    render(<SettingsPage />);
    expect(await screen.findByRole("heading", { name: "Telegram 告警" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

    await waitFor(() => expect(apiClient.updateSettings).toHaveBeenCalledWith({
      new_password: "",
      telegram_enabled: true,
      telegram_bot_token: "",
      telegram_chat_id: "",
    }));
    expect(await screen.findByRole("status")).toHaveTextContent("配置已保存。");
  });

  it("requires matching new passwords before saving", async () => {
    vi.mocked(apiClient.getSettings).mockResolvedValue({
      telegram_enabled: false,
      password_configured: true,
      managed_in_gui: true,
    });

    render(<SettingsPage />);
    fireEvent.change(await screen.findByLabelText("新密码"), { target: { value: "replacement-password" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "different-password" } });
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("两次输入的新密码不一致。");
    expect(apiClient.updateSettings).not.toHaveBeenCalled();
  });
});
