import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Layout } from "./components/Layout";

vi.mock("./auth", () => ({
  useAuth: () => ({
    me: {
      user_id: "u1",
      tenant_id: "t1",
      tenant_slug: "acme",
      email: "dono@acme.com",
      role: "owner",
    },
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout>conteúdo</Layout>
    </MemoryRouter>,
  );
}

describe("sidebar", () => {
  it("expõe as seções principais e mantém Recolher menu funcional", () => {
    localStorage.clear();
    renderLayout();

    expect(screen.getByRole("link", { name: /Dashboard/ })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /Construtor de Fluxos/ }),
    ).toBeTruthy();
    expect(screen.getAllByTitle("Disponível em breve").length).toBe(3);

    fireEvent.click(screen.getByLabelText("Recolher menu"));
    expect(document.querySelector(".sidebar-collapsed")).toBeTruthy();
    expect(localStorage.getItem("instarix:sidebar-collapsed")).toBe("1");
  });

  it("restaura a preferência de sidebar recolhida", () => {
    localStorage.setItem("instarix:sidebar-collapsed", "1");
    renderLayout();

    expect(document.querySelector(".sidebar-collapsed")).toBeTruthy();
    expect(screen.getByLabelText("Expandir menu")).toBeTruthy();
  });
});
