import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  api: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}));

import { api } from "./api";
import { AuthProvider, useAuth } from "./auth";

const currentUser = {
  user_id: "user-1",
  tenant_id: "tenant-1",
  tenant_slug: "acme",
  email: "owner@example.com",
  role: "owner",
};

const tokenPair = {
  access_token: "access-token",
  refresh_token: "refresh-token",
  token_type: "bearer",
  expires_in: 900,
};

function SessionProbe() {
  const { loading, login, me } = useAuth();
  return (
    <>
      <output data-testid="session">{loading ? "loading" : me?.email ?? "guest"}</output>
      <button type="button" onClick={() => void login("owner@example.com", "senha")}>
        Entrar
      </button>
    </>
  );
}

describe("AuthProvider", () => {
  const apiMock = vi.mocked(api);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("restaura a sessão pelo cookie no carregamento", async () => {
    apiMock.me.mockResolvedValue(currentUser);

    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("session")).toHaveTextContent("loading");
    await expect(screen.findByText("owner@example.com")).resolves.toBeVisible();
    expect(apiMock.me).toHaveBeenCalledTimes(1);
  });

  it("busca o perfil após login e reage à expiração da sessão", async () => {
    apiMock.me.mockResolvedValue(currentUser);
    apiMock.login.mockResolvedValue(tokenPair);

    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>,
    );

    await screen.findByText("owner@example.com");
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(apiMock.login).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(apiMock.me).toHaveBeenCalledTimes(2));

    act(() => window.dispatchEvent(new Event("instarix:auth-expired")));
    expect(screen.getByTestId("session")).toHaveTextContent("guest");
  });
});
