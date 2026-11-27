import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  CalendarClock,
  Copy,
  GitBranch,
  MessageCircle,
  Play,
  Plus,
  Save,
  Send,
  Trash2,
  Workflow,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { useToast } from "../toast";
import type {
  Account,
  Flow,
  FlowGraph,
  FlowNodeType,
  FlowRun,
} from "../types";
import { formatShortDate } from "../utils";

type FlowNodeData = {
  nodeType: FlowNodeType;
  config: Record<string, unknown>;
  executionStatus?: string;
};

type CanvasNode = Node<FlowNodeData>;

const NODE_CATEGORIES = [
  "Gatilhos",
  "Mensagens",
  "Lógica",
  "Dados",
  "Integrações",
] as const;

type NodeCategory = (typeof NODE_CATEGORIES)[number];

const NODE_OPTIONS: Array<{
  type: FlowNodeType;
  label: string;
  icon: typeof Zap;
  hint: string;
  category: NodeCategory;
}> = [
  {
    type: "trigger.manual",
    label: "Gatilho manual",
    icon: Zap,
    hint: "Inicia o fluxo quando você testar",
    category: "Gatilhos",
  },
  {
    type: "condition.keyword",
    label: "Se contém palavra",
    icon: GitBranch,
    hint: "Separa o fluxo em sim/não",
    category: "Lógica",
  },
  {
    type: "action.reply_dm",
    label: "Responder DM",
    icon: MessageCircle,
    hint: "Resposta real quando há thread_id",
    category: "Mensagens",
  },
  {
    type: "action.reply_comment",
    label: "Responder comentário",
    icon: MessageCircle,
    hint: "Resposta real quando há comment_id",
    category: "Mensagens",
  },
  {
    type: "action.publish",
    label: "Publicar mídia",
    icon: Send,
    hint: "Cria um job de publicação real",
    category: "Integrações",
  },
  {
    type: "action.schedule_publish",
    label: "Agendar publicação",
    icon: CalendarClock,
    hint: "Publica na data e hora escolhidas",
    category: "Integrações",
  },
];

function nodeCategory(type: FlowNodeType): NodeCategory {
  return (
    NODE_OPTIONS.find((option) => option.type === type)?.category ?? "Dados"
  );
}

function categorySlug(category: NodeCategory): string {
  return category
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z]/g, "");
}

function toLocalInput(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function nodeTitle(data: FlowNodeData): string {
  return (
    String(data.config.label ?? "") ||
    NODE_OPTIONS.find((option) => option.type === data.nodeType)?.label ||
    data.nodeType
  );
}

function nodeSubtitle(data: FlowNodeData): string {
  const config = data.config;
  if (config.node_description) return String(config.node_description);
  if (data.nodeType === "condition.keyword") {
    return config.keyword ? `palavra: ${String(config.keyword)}` : "configure a palavra";
  }
  if (data.nodeType === "action.reply_dm" || data.nodeType === "action.reply_comment") {
    return config.message ? String(config.message) : "configure a mensagem";
  }
  if (data.nodeType === "action.publish") {
    return String(config.type ?? "publish.photo");
  }
  if (data.nodeType === "action.schedule_publish") {
    return config.run_after ? `em ${String(config.run_after)}` : "defina a data e hora";
  }
  return "toque para executar";
}

function nodeConfigProblem(node: CanvasNode): string | null {
  const config = node.data.config;
  switch (node.data.nodeType) {
    case "condition.keyword":
      return config.keyword ? null : "Informe a palavra-chave.";
    case "action.reply_dm":
    case "action.reply_comment":
      return config.message ? null : "Informe a mensagem.";
    case "action.publish":
    case "action.schedule_publish":
      if (!config.storage_key) return "Informe a chave do arquivo.";
      if (
        node.data.nodeType === "action.schedule_publish" &&
        !config.run_after
      ) {
        return "Defina a data e hora da publicação.";
      }
      return null;
    default:
      return null;
  }
}

function FlowNodeCard({ data, selected }: NodeProps<CanvasNode>) {
  const isTrigger = data.nodeType === "trigger.manual";
  const isCondition = data.nodeType === "condition.keyword";
  return (
    <div
      className={`flow-node flow-node-${categorySlug(nodeCategory(data.nodeType))} ${selected ? "flow-node-selected" : ""}`}
    >
      {!isTrigger && <Handle type="target" position={Position.Left} />}
      {data.executionStatus && (
        <span className={`flow-node-badge status-${data.executionStatus}`}>
          {data.executionStatus === "ok" ? "ok" : "erro"}
        </span>
      )}
      <div className="flow-node-title">{nodeTitle(data)}</div>
      <div className="flow-node-subtitle">{nodeSubtitle(data)}</div>
      {(isCondition || !isTrigger) && (
        <div className="flow-node-handles">
          {isCondition ? (
            <>
              <div className="flow-handle-label">
                sim <Handle type="source" id="true" position={Position.Right} />
              </div>
              <div className="flow-handle-label">
                não <Handle type="source" id="false" position={Position.Right} />
              </div>
            </>
          ) : (
            <Handle type="source" id="out" position={Position.Right} />
          )}
        </div>
      )}
    </div>
  );
}

const nodeTypes = { flowNode: FlowNodeCard };

function graphToCanvas(graph: FlowGraph): {
  nodes: CanvasNode[];
  edges: Edge[];
} {
  return {
    nodes: graph.nodes.map((node, index) => ({
      id: node.id,
      type: "flowNode",
      position: node.position ?? { x: 80 + index * 250, y: 100 },
      data: { nodeType: node.type, config: node.config },
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.source_handle ?? undefined,
      markerEnd: { type: MarkerType.ArrowClosed },
    })),
  };
}

function canvasToGraph(nodes: CanvasNode[], edges: Edge[]): FlowGraph {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.data.nodeType,
      config: node.data.config,
      position: { x: node.position.x, y: node.position.y },
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_handle: edge.sourceHandle ?? null,
    })),
  };
}

function snapshotOf(data: {
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  triggerSource: Flow["trigger_source"];
  accountId: string;
  interval: number;
  graph: FlowGraph;
}): string {
  return JSON.stringify(data);
}

export function FlowsPage() {
  const { notify } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [flows, setFlows] = useState<Flow[]>([]);
  const [flowId, setFlowId] = useState<string | null>(null);
  const [name, setName] = useState("Novo fluxo");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("geral");
  const [enabled, setEnabled] = useState(true);
  const [triggerSource, setTriggerSource] = useState<Flow["trigger_source"]>("manual");
  const [triggerAccountId, setTriggerAccountId] = useState("");
  const [pollInterval, setPollInterval] = useState(30);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [testText, setTestText] = useState("");
  const [run, setRun] = useState<FlowRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedSnapshot, setSavedSnapshot] = useState("");

  const currentSnapshot = snapshotOf({
    name,
    description,
    category,
    enabled,
    triggerSource,
    accountId: triggerAccountId,
    interval: pollInterval,
    graph: canvasToGraph(nodes, edges),
  });
  const dirty = savedSnapshot !== "" && currentSnapshot !== savedSnapshot;

  const statusByNode = useMemo(
    () =>
      Object.fromEntries(
        (run?.steps ?? []).map((step) => [step.node_id, step.status]),
      ),
    [run],
  );
  const decoratedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: { ...node.data, executionStatus: statusByNode[node.id] },
      })),
    [nodes, statusByNode],
  );

  const load = useCallback(async (applyFirst = true) => {
    setLoading(true);
    try {
      const [list, accountPage] = await Promise.all([
        api.flows(),
        api.accounts(100),
      ]);
      setFlows(list);
      setAccounts(accountPage.items);
      if (applyFirst && list.length) {
        const requested = searchParams.get("id");
        const first = list.find((item) => item.id === requested) ?? list[0];
        setFlowId(first.id);
        setName(first.name);
        setDescription(first.description ?? "");
        setCategory(first.category);
        setEnabled(first.enabled);
        setTriggerSource(first.trigger_source);
        setTriggerAccountId(first.account_id ?? "");
        setPollInterval(first.poll_interval_seconds);
        const canvas = graphToCanvas(first.graph);
        setNodes(canvas.nodes);
        setEdges(canvas.edges);
        setSavedSnapshot(
          snapshotOf({
            name: first.name,
            description: first.description ?? "",
            category: first.category,
            enabled: first.enabled,
            triggerSource: first.trigger_source,
            accountId: first.account_id ?? "",
            interval: first.poll_interval_seconds,
            graph: first.graph,
          }),
        );
      }
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao carregar fluxos.",
        "error",
      );
    } finally {
      setLoading(false);
    }
  }, [notify, searchParams, setEdges, setNodes]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => nodes.find((node) => node.id === selectedId) ?? null,
    [nodes, selectedId],
  );

  const configProblem = useMemo(
    () => (selected ? nodeConfigProblem(selected) : null),
    [selected],
  );

  function selectFlow(flow: Flow) {
    setFlowId(flow.id);
    setName(flow.name);
    setDescription(flow.description ?? "");
    setCategory(flow.category);
    setEnabled(flow.enabled);
    setTriggerSource(flow.trigger_source);
    setTriggerAccountId(flow.account_id ?? "");
    setPollInterval(flow.poll_interval_seconds);
    const canvas = graphToCanvas(flow.graph);
    setNodes(canvas.nodes);
    setEdges(canvas.edges);
    setSavedSnapshot(
      snapshotOf({
        name: flow.name,
        description: flow.description ?? "",
        category: flow.category,
        enabled: flow.enabled,
        triggerSource: flow.trigger_source,
        accountId: flow.account_id ?? "",
        interval: flow.poll_interval_seconds,
        graph: flow.graph,
      }),
    );
    setSelectedId(null);
    setRun(null);
  }

  function newFlow() {
    setFlowId(null);
    setName("Novo fluxo");
    setDescription("");
    setCategory("geral");
    setEnabled(true);
    setTriggerSource("manual");
    setTriggerAccountId("");
    setPollInterval(30);
    setNodes([]);
    setEdges([]);
    setSelectedId(null);
    setRun(null);
    setSavedSnapshot("");
    setSearchParams({}, { replace: true });
  }

  function addNode(type: FlowNodeType) {
    const id = `${type.replaceAll(".", "-")}-${Date.now().toString(36)}`;
    setNodes((current) => [
      ...current,
      {
        id,
        type: "flowNode",
        position: { x: 120 + current.length * 60, y: 120 + current.length * 50 },
        data: { nodeType: type, config: {} },
      },
    ]);
    setSelectedId(id);
  }

  function duplicateNode() {
    if (!selected) return;
    const id = `${selected.data.nodeType.replaceAll(".", "-")}-${Date.now().toString(36)}`;
    setNodes((current) => [
      ...current,
      {
        ...selected,
        id,
        position: { x: selected.position.x + 40, y: selected.position.y + 60 },
        selected: false,
        data: { ...selected.data },
      },
    ]);
    setSelectedId(id);
  }

  function setConfig(key: string, value: unknown) {
    if (!selectedId) return;
    setNodes((current) =>
      current.map((node) =>
        node.id === selectedId
          ? {
              ...node,
              data: {
                ...node.data,
                config: { ...node.data.config, [key]: value },
              },
            }
          : node,
      ),
    );
  }

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((current) =>
        addEdge(
          { ...connection, markerEnd: { type: MarkerType.ArrowClosed } },
          current,
        ),
      ),
    [setEdges],
  );

  function validateGraph(): string | null {
    if (!name.trim()) return "Informe um nome para o fluxo.";
    if (nodes.length === 0) return "Adicione ao menos um nó gatilho.";
    if (!nodes.some((node) => node.data.nodeType === "trigger.manual")) {
      return "Adicione um nó gatilho manual.";
    }
    if (triggerSource !== "manual" && !triggerAccountId) {
      return "Escolha a conta que vai receber as mensagens/comentários.";
    }
    const invalidNode = nodes.find((node) => nodeConfigProblem(node));
    if (invalidNode) {
      const problem = nodeConfigProblem(invalidNode);
      return `Nó ${nodeTitle(invalidNode.data)}: ${problem}`;
    }
    return null;
  }

  async function save() {
    const problem = validateGraph();
    if (problem) {
      notify(problem, "error");
      return;
    }
    setSaving(true);
    try {
      const graph = canvasToGraph(nodes, edges);
      if (flowId) {
        await api.updateFlow(flowId, {
          name: name.trim(),
          description: description.trim() || null,
          category,
          enabled,
          graph,
          trigger_source: triggerSource,
          account_id: triggerSource === "manual" ? null : triggerAccountId || null,
          poll_interval_seconds: pollInterval,
        });
        notify("Fluxo salvo.", "success");
      } else {
        const created = await api.createFlow({
          name: name.trim(),
          description: description.trim() || null,
          category,
          enabled,
          graph,
          trigger_source: triggerSource,
          account_id: triggerSource === "manual" ? null : triggerAccountId || null,
          poll_interval_seconds: pollInterval,
        });
        setFlowId(created.id);
        setSearchParams({ id: created.id }, { replace: true });
        notify("Fluxo criado.", "success");
      }
      setSavedSnapshot(currentSnapshot);
      await load(false);
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao salvar.", "error");
    } finally {
      setSaving(false);
    }
  }

  async function runFlow() {
    if (!flowId) {
      notify("Salve o fluxo antes de testar.", "error");
      return;
    }
    try {
      const result = await api.runFlow(flowId, {
        trigger: "manual",
        context: { input_text: testText },
      });
      setRun(result);
      notify(
        result.status === "succeeded"
          ? "Fluxo executado com sucesso."
          : "O fluxo terminou com erro.",
        result.status === "succeeded" ? "success" : "error",
      );
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao executar.", "error");
    }
  }

  async function removeFlow() {
    if (!flowId || !window.confirm(`Excluir o fluxo "${name}"?`)) return;
    try {
      await api.deleteFlow(flowId);
      notify("Fluxo excluído.", "success");
      newFlow();
      await load();
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao excluir.", "error");
    }
  }

  if (loading) return <Spinner label="Carregando fluxos" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Automações"
        title="Fluxos"
        description="Monte o caminho: gatilho → condição → ação. Arraste os nós e ligue as saídas."
      />

      <div className="flow-layout">
        <aside className="panel flow-list">
          <div className="panel-header">
            <div>
              <h2>Meus fluxos</h2>
              <p>{flows.length} salvos</p>
            </div>
            <button
              type="button"
              className="icon-button"
              onClick={newFlow}
              aria-label="Novo fluxo"
            >
              <Plus size={16} />
            </button>
          </div>
          {flows.length === 0 ? (
            <p className="muted">Nenhum fluxo salvo ainda.</p>
          ) : (
            <div className="flow-list-items">
              {flows.map((flow) => (
                <button
                  key={flow.id}
                  type="button"
                  className={`flow-list-item ${flow.id === flowId ? "active" : ""}`}
                  onClick={() => selectFlow(flow)}
                >
                  <Workflow size={15} />
                  <span>
                    <strong>{flow.name}</strong>
                    <small>{formatShortDate(flow.updated_at)}</small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </aside>

        <section className="panel flow-editor">
          <div className="flow-toolbar">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-label="Nome do fluxo"
              placeholder="Nome do fluxo"
            />
            {dirty && (
              <span className="dirty-badge" title="Alterações não salvas">
                não salvo
              </span>
            )}
            <span className={`status status-${enabled ? "active" : "disabled"}`}>
              {enabled ? "Ativo" : "Pausado"}
            </span>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              Ativo
            </label>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => void save()}
              disabled={saving}
            >
              <Save size={15} />
              {saving ? "Salvando…" : "Salvar"}
            </button>
            <button
              type="button"
              className="button button-primary"
              onClick={() => void runFlow()}
            >
              <Play size={15} />
              Testar
            </button>
            {flowId && (
              <button
                type="button"
                className="icon-button icon-danger"
                onClick={() => void removeFlow()}
                aria-label="Excluir fluxo"
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>

          <div className="flow-workspace">
            <div className="flow-canvas">
              <ReactFlow<CanvasNode, Edge>
                nodes={decoratedNodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={(_, node) => setSelectedId(node.id)}
                fitView
              >
                <Background />
                <Controls />
                <MiniMap pannable zoomable />
              </ReactFlow>
              {nodes.length === 0 && (
                <div className="flow-canvas-empty">
                  <EmptyState
                    icon={Workflow}
                    title="Comece pelo gatilho"
                    description="Adicione um nó à esquerda e ligue as saídas até a última ação."
                  />
                </div>
              )}
            </div>

            <aside className="flow-side">
              <div className="flow-meta-config">
                <h3>Fluxo</h3>
                <label className="field">
                  <span>Descrição</span>
                  <textarea
                    rows={2}
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="O que este fluxo faz?"
                  />
                </label>
                <label className="field">
                  <span>Categoria</span>
                  <input
                    value={category}
                    onChange={(event) => setCategory(event.target.value)}
                    placeholder="geral"
                  />
                </label>
              </div>

              <div className="flow-trigger-config">
                <h3>Gatilho</h3>
                <label className="field">
                  <span>Origem</span>
                  <select
                    value={triggerSource}
                    onChange={(event) =>
                      setTriggerSource(event.target.value as Flow["trigger_source"])
                    }
                  >
                    <option value="manual">Somente teste manual</option>
                    <option value="dm">DMs recebidas (polling)</option>
                    <option value="comment">Comentários (polling)</option>
                  </select>
                </label>
                {triggerSource !== "manual" && (
                  <>
                    <label className="field">
                      <span>Conta</span>
                      <select
                        value={triggerAccountId}
                        onChange={(event) => setTriggerAccountId(event.target.value)}
                      >
                        <option value="">Selecione</option>
                        {accounts.map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.label} (@{account.username})
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Intervalo (segundos)</span>
                      <input
                        type="number"
                        min={5}
                        max={3600}
                        value={pollInterval}
                        onChange={(event) => setPollInterval(Number(event.target.value))}
                      />
                      <small>
                        O worker consulta o Instagram nesse intervalo, uma vez por conta.
                      </small>
                    </label>
                  </>
                )}
              </div>

              <div className="flow-palette">
                <h3>Adicionar nó</h3>
                {NODE_CATEGORIES.map((categoryName) => {
                  const options = NODE_OPTIONS.filter(
                    (option) => option.category === categoryName,
                  );
                  if (!options.length) return null;
                  return (
                    <div key={categoryName} className="flow-palette-group">
                      <span
                        className={`flow-category-title flow-category-${categorySlug(categoryName)}`}
                      >
                        {categoryName}
                      </span>
                      {options.map((option) => (
                        <button
                          key={option.type}
                          type="button"
                          className="flow-palette-item"
                          onClick={() => addNode(option.type)}
                        >
                          <option.icon size={16} />
                          <span>
                            <strong>{option.label}</strong>
                            <small>{option.hint}</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  );
                })}
              </div>

              {selected && (
                <div className="flow-config">
                  <h3>Configurar nó</h3>
                  <p className="muted">{nodeTitle(selected.data)}</p>
                  <label className="field">
                    <span>Nome do nó</span>
                    <input
                      value={String(selected.data.config.label ?? "")}
                      onChange={(event) => setConfig("label", event.target.value)}
                      placeholder={nodeTitle({ ...selected.data, config: {} })}
                    />
                  </label>
                  <label className="field">
                    <span>Descrição</span>
                    <textarea
                      rows={2}
                      value={String(selected.data.config.node_description ?? "")}
                      onChange={(event) =>
                        setConfig("node_description", event.target.value)
                      }
                      placeholder="O que este nó faz?"
                    />
                  </label>
                  {configProblem && <div className="form-error">{configProblem}</div>}
                  {selected.data.nodeType === "condition.keyword" && (
                    <>
                      <label className="field">
                        <span>Campo</span>
                        <input
                          value={String(selected.data.config.field ?? "input_text")}
                          onChange={(event) => setConfig("field", event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Palavra-chave</span>
                        <input
                          value={String(selected.data.config.keyword ?? "")}
                          onChange={(event) => setConfig("keyword", event.target.value)}
                          placeholder="link"
                        />
                      </label>
                      <label className="field">
                        <span>Comparação</span>
                        <select
                          value={String(selected.data.config.mode ?? "contains")}
                          onChange={(event) => setConfig("mode", event.target.value)}
                        >
                          <option value="contains">Contém</option>
                          <option value="equals">É igual a</option>
                        </select>
                      </label>
                    </>
                  )}
                  {(selected.data.nodeType === "action.reply_dm" ||
                    selected.data.nodeType === "action.reply_comment") && (
                    <label className="field">
                      <span>Mensagem</span>
                      <textarea
                        rows={4}
                        value={String(selected.data.config.message ?? "")}
                        onChange={(event) => setConfig("message", event.target.value)}
                        placeholder="Segue o link…"
                      />
                      <small>Resposta simulada nesta fase.</small>
                    </label>
                  )}
                  {(selected.data.nodeType === "action.publish" ||
                    selected.data.nodeType === "action.schedule_publish") && (
                    <>
                      <label className="field">
                        <span>Conta</span>
                        <select
                          value={String(selected.data.config.account_id ?? "")}
                          onChange={(event) => setConfig("account_id", event.target.value)}
                        >
                          <option value="">Da execução</option>
                          {accounts.map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.label} (@{account.username})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Formato</span>
                        <select
                          value={String(selected.data.config.type ?? "publish.photo")}
                          onChange={(event) => setConfig("type", event.target.value)}
                        >
                          <option value="publish.photo">Foto</option>
                          <option value="publish.video">Vídeo</option>
                          <option value="publish.reel">Reel</option>
                          <option value="publish.story">Story</option>
                          <option value="publish.album">Álbum</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>
                          <CalendarClock size={14} />
                          {selected.data.nodeType === "action.schedule_publish"
                            ? "Agendar para"
                            : "Agendar para (opcional)"}
                        </span>
                        <input
                          type="datetime-local"
                          value={
                            selected.data.config.run_after
                              ? toLocalInput(String(selected.data.config.run_after))
                              : ""
                          }
                          onChange={(event) =>
                            setConfig(
                              "run_after",
                              event.target.value
                                ? new Date(event.target.value).toISOString()
                                : "",
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Chave do arquivo</span>
                        <input
                          value={String(selected.data.config.storage_key ?? "")}
                          onChange={(event) =>
                            setConfig("storage_key", event.target.value)
                          }
                          placeholder="tenant/conta/foto.jpg"
                        />
                        <small>
                          Envie o arquivo em Publicar e copie a chave do upload.
                        </small>
                      </label>
                      <label className="field">
                        <span>Legenda</span>
                        <textarea
                          rows={3}
                          value={String(selected.data.config.caption ?? "")}
                          onChange={(event) => setConfig("caption", event.target.value)}
                        />
                      </label>
                    </>
                  )}
                  <div className="flow-node-actions">
                    <button
                      type="button"
                      className="button button-primary button-small"
                      onClick={() => void save()}
                      disabled={saving || Boolean(configProblem)}
                    >
                      <Save size={13} />
                      Salvar
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={duplicateNode}
                      title="Duplicar nó"
                      aria-label="Duplicar nó"
                    >
                      <Copy size={14} />
                    </button>
                    <button
                      type="button"
                      className="icon-button icon-danger"
                      onClick={() =>
                        setNodes((current) =>
                          current.filter((node) => node.id !== selected.id),
                        )
                      }
                      title="Remover nó"
                      aria-label="Remover nó"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              )}

              <div className="flow-test">
                <h3>Testar manualmente</h3>
                <label className="field">
                  <span>Mensagem de exemplo</span>
                  <input
                    value={testText}
                    onChange={(event) => setTestText(event.target.value)}
                    placeholder="quero o link"
                  />
                </label>
              </div>
            </aside>
          </div>

          {run && (
            <div className="flow-run-result">
              <div className="panel-header">
                <div>
                  <h2>Última execução</h2>
                  <p>
                    {run.status} · {run.steps.length} etapa(s)
                  </p>
                </div>
              </div>
              {run.error_message && <div className="error-banner">{run.error_message}</div>}
              <ol className="flow-steps">
                {run.steps.map((step, index) => (
                  <li key={`${step.node_id}-${index}`}>
                    <span className={`status status-${step.status}`}>
                      {step.status === "ok" ? "ok" : "erro"}
                    </span>
                    <div>
                      <strong>{step.type}</strong>
                      <code>{JSON.stringify(step.detail)}</code>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
