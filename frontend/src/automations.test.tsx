import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AutomationsPage } from "./pages/AutomationsPage";

const flow = {
  id: "f1",
  name: "Boas-vindas",
  description: "Responde quem chega",
  category: "atendimento",
  enabled: true,
  graph: { nodes: [], edges: [] },
  trigger_source: "manual" as const,
  account_id: null,
  poll_interval_seconds: 30,
  created_at: "2026-11-27T12:00:00Z",
  updated_at: "2026-11-27T12:00:00Z",
};

const paused = { ...flow, id: "f2", name: "Antigo", enabled: false };

const mocks = vi.hoisted(() => ({
  flows: vi.fn(),
  flowRuns: vi.fn(),
  updateFlow: vi.fn(),
  createFlow: vi.fn(),
  deleteFlow: vi.fn(),
  notify: vi.fn(),
}));

vi.mock("./api", () => ({
  api: {
    flows: mocks.flows,
    flowRuns: mocks.flowRuns,
    updateFlow: mocks.updateFlow,
    createFlow: mocks.createFlow,
    deleteFlow: mocks.deleteFlow,
  },
  ApiError: class ApiError extends Error {},
}));

vi.mock("./toast", () => ({
  useToast: () => ({ notify: mocks.notify }),
}));

describe("Automações", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.flows.mockResolvedValue([flow, paused]);
    mocks.flowRuns.mockImplementation(async (id: string) =>
      id === "f1"
        ? [
            {
              id: "r1",
              flow_id: "f1",
              status: "succeeded",
              trigger: "manual",
              context: {},
              steps: [],
              error_code: null,
              error_message: null,
              created_at: "2026-11-27T12:00:00Z",
              finished_at: "2026-11-27T12:00:01Z",
            },
          ]
        : [],
    );
  });

  it("lista fluxos com status derivado e filtra por busca", async () => {
    render(
      <MemoryRouter>
        <AutomationsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Boas-vindas")).toBeTruthy();
    expect(screen.getByText("Antigo")).toBeTruthy();
    expect(screen.getByText("ativa")).toBeTruthy();
    expect(screen.getByText("rascunho")).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("Buscar por nome ou descrição"), {
      target: { value: "Antigo" },
    });
    expect(screen.queryByText("Boas-vindas")).toBeNull();
    expect(screen.getByText("Antigo")).toBeTruthy();
  });

  it("pausa um fluxo ativo", async () => {
    render(
      <MemoryRouter>
        <AutomationsPage />
      </MemoryRouter>,
    );
    await screen.findByText("Boas-vindas");

    fireEvent.click(screen.getAllByLabelText("Pausar")[0]);
    expect(mocks.updateFlow).toHaveBeenCalledWith("f1", { enabled: false });
  });
});
