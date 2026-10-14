import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { inspectCandidates } from "./lease-selection.mjs";

type Observer = (roots: string[], options: { timeoutMs: number; signal: AbortSignal }) => Promise<unknown[]>;

export function registerNextSafe(pi: ExtensionAPI, loadObserver: () => Promise<Observer>) {
	pi.registerTool({
		name: "next_safe",
		label: "Inspect task source leases",
		description: "Read-only /next safe listing or fresh recheck of a qualified selector. Uses explicit bead source_scope declarations and the public in-process Pi lease observer. Never claims work or acquires/releases leases. Free observations are advisory, not reservations or source authority.",
		parameters: Type.Object({
			action: Type.Union([Type.Literal("list"), Type.Literal("recheck")]),
			selector: Type.Optional(Type.String({ maxLength: 512 })),
		}, { additionalProperties: false }),
		annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
		async execute(_id, params, signal, _update, ctx) {
			if ((params.action === "recheck") !== Boolean(params.selector)) throw new Error("Only recheck requires a qualified selector");
			const result = await inspectCandidates(ctx.cwd, { selector: params.selector, signal, loadObserver });
			const details = { ...result, sessionId: ctx.sessionManager.getSessionId(), cwd: ctx.cwd };
			return { content: [{ type: "text", text: JSON.stringify(details) }], details };
		},
	});
}

export default function (pi: ExtensionAPI) {
	registerNextSafe(pi, async () => (await import("@flurdy/pi-session-mode/lease-observer")).probeWorktreeLeaseOccupancies);
}
