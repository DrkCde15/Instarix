import { describe, expect, it } from "vitest";
import { idempotencyKeyFor, randomIdempotencyKey } from "./utils";

describe("randomIdempotencyKey", () => {
  it("gera chaves únicas e não vazias", () => {
    const keys = new Set(
      Array.from({ length: 20 }, () => randomIdempotencyKey()),
    );

    expect(keys.size).toBe(20);
    for (const key of keys) expect(key.length).toBeGreaterThan(0);
  });
});

describe("idempotencyKeyFor", () => {
  it("mantém a chave no retry do mesmo rascunho e troca ao editar", () => {
    const first = idempotencyKeyFor(null, "rascunho-a");
    const retry = idempotencyKeyFor(first, "rascunho-a");
    const edited = idempotencyKeyFor(retry, "rascunho-b");

    expect(retry.key).toBe(first.key);
    expect(edited.key).not.toBe(first.key);
  });
});
