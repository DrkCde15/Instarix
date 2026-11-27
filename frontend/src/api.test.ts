import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, tokens } from "./api";

const tokenPair = {
  access_token: "access-new",
  refresh_token: "refresh-new",
  token_type: "bearer",
  expires_in: 900,
};

const currentUser = {
  user_id: "user-1",
  tenant_id: "tenant-1",
  tenant_slug: "acme",
  email: "owner@example.com",
  role: "owner",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    tokens.clear();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("autentica e mantém o access token apenas em memória", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, tokenPair));

    await expect(api.login("owner@example.com", "senha-forte")).resolves.toEqual(
      tokenPair,
    );

    expect(tokens.access()).toBe("access-new");
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/auth/token",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(request.headers).get("Authorization")).toBeNull();
    expect(new Headers(request.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("renova a sessão após 401 e repete a requisição com o novo token", async () => {
    tokens.set({ ...tokenPair, access_token: "access-old" });
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "expired" } }))
      .mockResolvedValueOnce(jsonResponse(200, tokenPair))
      .mockResolvedValueOnce(jsonResponse(200, currentUser));

    await expect(api.me()).resolves.toEqual(currentUser);

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/auth/refresh",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    const retry = fetchMock.mock.calls[2][1] as RequestInit;
    expect(new Headers(retry.headers).get("Authorization")).toBe(
      "Bearer access-new",
    );
  });

  it("compartilha um único refresh entre requisições concorrentes", async () => {
    tokens.set({ ...tokenPair, access_token: "access-old" });
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "expired" } }))
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "expired" } }))
      .mockResolvedValueOnce(jsonResponse(200, tokenPair))
      .mockResolvedValueOnce(jsonResponse(200, currentUser))
      .mockResolvedValueOnce(jsonResponse(200, currentUser));

    await expect(Promise.all([api.me(), api.me()])).resolves.toEqual([
      currentUser,
      currentUser,
    ]);

    expect(
      fetchMock.mock.calls.filter(([url]) => url === "/v1/auth/refresh"),
    ).toHaveLength(1);
  });

  it("encerra a sessão uma única vez se o refresh falhar", async () => {
    const onExpired = vi.fn();
    window.addEventListener("instarix:auth-expired", onExpired);
    tokens.set({ ...tokenPair, access_token: "access-old" });
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse(401, {
          error: { code: "invalid_token", message: "Token expirado." },
        }),
      )
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "invalid_refresh" } }));

    await expect(api.me()).rejects.toEqual(
      expect.objectContaining({
        status: 401,
        code: "invalid_token",
      }),
    );

    expect(tokens.access()).toBeNull();
    expect(onExpired).toHaveBeenCalledTimes(1);
    window.removeEventListener("instarix:auth-expired", onExpired);
  });
});
