import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";

/** Impactos que reprovam o teste (RNF-014: 0 violações serious/critical). */
const BLOCKING = new Set(["serious", "critical"]);

/**
 * Exceções explícitas por regra do axe. Vazio de propósito: qualquer entrada exige motivo
 * escrito aqui, referência em docs/16 e aprovação humana (AGENTS.md §7/§11).
 */
export const A11Y_EXCEPTIONS: Record<string, string> = {};

/** Roda o axe-core na página atual e falha se houver violação serious/critical. */
export async function auditA11y(page: Page, testInfo: TestInfo, label: string): Promise<void> {
  await page.waitForLoadState("networkidle");
  const results = await new AxeBuilder({ page }).analyze();
  await testInfo.attach(`axe-${label}`, {
    body: JSON.stringify(results.violations, null, 2),
    contentType: "application/json",
  });
  const blocking = results.violations.filter((v) => BLOCKING.has(v.impact ?? "") && !(v.id in A11Y_EXCEPTIONS));
  if (blocking.length === 0) return;
  const lines = blocking.map((v) => {
    const nodes = v.nodes
      .slice(0, 4)
      .map((n) => `${n.target.join(" ")} :: ${(n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 280)}`)
      .join(" | ");
    return `  - ${v.id} (${v.impact}): ${v.help} [${v.nodes.length} nó(s)] ${nodes}`;
  });
  throw new Error(`axe em "${label}": ${blocking.length} violação(ões) serious/critical\n${lines.join("\n")}`);
}
