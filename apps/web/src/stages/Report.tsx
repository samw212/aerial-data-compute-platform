/* Report: the persisted runs of this scenario, a comparison of two, the PDF. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { CoverageDelta, CoverageRun } from "../api/contracts";
import { useRuns } from "../api/queries";
import { Shell } from "../app/Shell";
import { Dock, DockFooter, DockHeader, DockTabs, Empty, Tag } from "../components/ui";
import { useStageContext } from "./useStageContext";

const TIERS = ["identify", "recognise", "observe", "detect"] as const;

export function ReportStage() {
  const ctx = useStageContext("Report");
  const { venue, scenario, scenarioId } = ctx;
  const runs = useRuns(scenarioId);
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);
  const [tab, setTab] = useState("Runs");
  const list = runs.data ?? [];
  const runA = list.find((r) => r.id === a) ?? list[1] ?? null;
  const runB = list.find((r) => r.id === b) ?? list[0] ?? null;
  const delta = useQuery({
    queryKey: ["/api/coverage/compare", runA?.id, runB?.id],
    queryFn: () => api.post<CoverageDelta>("/api/coverage/compare", { run_a: runA!.id, run_b: runB!.id }),
    enabled: !!runA && !!runB && runA.id !== runB.id,
    retry: false,
  });
  const pct = (r: CoverageRun, t: string) => (100 * ((r.stats.tier_area_m2 as Record<string, number>)[t] ?? 0)) / r.stats.area_m2;
  const blind = (r: CoverageRun) => (100 * r.stats.blind_m2) / r.stats.area_m2;
  const imgs = useMemo(() => ({ a: runA ? `/api/coverage-runs/${runA.id}/grid.png?scale=3` : null, b: runB ? `/api/coverage-runs/${runB.id}/grid.png?scale=3` : null, d: runA && runB && runA.id !== runB.id ? `/api/coverage/compare.png?run_a=${runA.id}&run_b=${runB.id}&scale=3` : null }), [runA, runB]);

  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${scenario?.name ?? "…"}`} stages={ctx.links}>
      <div style={{ position: "absolute", inset: 0, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 1, background: "var(--color-line-2)", paddingRight: 396 }}>
        {[["A", imgs.a, runA], ["B", imgs.b, runB], ["Δ", imgs.d, null]].map(([k, src, r]) => (
          <div key={k as string} style={{ background: "var(--color-bg)", position: "relative", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            {src ? <img src={src as string} alt="" style={{ maxWidth: "94%", maxHeight: "80%", imageRendering: "pixelated", border: "1px solid var(--color-line)" }} /> : <Empty title={k === "Δ" ? "Pick two different runs" : "No run"} />}
            <div className="m" style={{ position: "absolute", left: 14, top: 12, fontSize: 11, color: "var(--color-ink-2)" }}>{k as string}{r ? ` · ${(r as CoverageRun).id.slice(0, 8)} · ${(r as CoverageRun).grid_spacing_m} m · tents ${(r as CoverageRun).include_tents ? "on" : "off"}` : k === "Δ" ? " · newly blind red, newly covered green" : ""}</div>
          </div>
        ))}
      </div>
      <Dock width={372}>
        <DockHeader eyebrow="Report" title={scenario?.name ?? "…"} meta={`${list.length} persisted runs · every number from the persisted run, never recomputed`} />
        <DockTabs tabs={["Runs", "Compare"]} active={tab} onPick={setTab} />
        {tab === "Runs" && (
          <div className="scroll" style={{ flex: 1 }}>
            {list.map((r) => (
              <div key={r.id} style={{ padding: "8px 14px", borderBottom: "1px solid var(--color-line)" }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="m" style={{ fontSize: 12 }}>{r.id.slice(0, 8)}</span>
                  <span className="row" style={{ gap: 4 }}>
                    <button className={`tag ${runA?.id === r.id ? "t-acc" : "t-mute"}`} style={{ border: "none", cursor: "pointer" }} onClick={() => setA(r.id)}>A</button>
                    <button className={`tag ${runB?.id === r.id ? "t-acc" : "t-mute"}`} style={{ border: "none", cursor: "pointer" }} onClick={() => setB(r.id)}>B</button>
                  </span>
                </div>
                <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 2 }}>{r.computed_at?.slice(0, 16).replace("T", " ")} · {r.grid_spacing_m} m · tents {r.include_tents ? "on" : "off"} · kernel {r.kernel_version} · {r.created_by ?? ""}</div>
                <div className="m" style={{ fontSize: 11, marginTop: 2 }}>detect {pct(r, "detect").toFixed(1)}% · observe {pct(r, "observe").toFixed(1)}% · blind {blind(r).toFixed(1)}%</div>
              </div>
            ))}
            {!list.length && <Empty title="No runs" hint="Run on server in Plan first." />}
          </div>
        )}
        {tab === "Compare" && (
          <div style={{ padding: "12px 14px", flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
            {runA && runB ? (
              <>
                <div className="row" style={{ justifyContent: "space-between", fontSize: 10.5, color: "var(--color-ink-3)" }}><span style={{ flex: 1 }}>tier</span><span style={{ width: 56, textAlign: "right" }}>A</span><span style={{ width: 56, textAlign: "right" }}>B</span><span style={{ width: 70, textAlign: "right" }}>Δ</span></div>
                {TIERS.map((t) => <DRow key={t} label={`${t[0]!.toUpperCase()}${t.slice(1)} or better`} a={pct(runA, t)} b={pct(runB, t)} />)}
                <DRow label="Blind" a={blind(runA)} b={blind(runB)} badUp />
                <DRow label="Seen by 2+" a={(100 * runA.stats.redundant_2plus_m2) / runA.stats.area_m2} b={(100 * runB.stats.redundant_2plus_m2) / runB.stats.area_m2} />
                <div style={{ marginTop: 10 }}>
                  <div className="lbl" style={{ fontSize: 9.5 }}>Newly without sightline</div>
                  <div className="m" style={{ fontSize: 22, color: "var(--color-bad)" }}>{delta.data ? `${delta.data.newly_blind_m2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²` : delta.error ? <span style={{ fontSize: 12 }}>{String((delta.error as Error).message)}</span> : "…"}</div>
                  {delta.data && <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)" }}>newly covered {delta.data.newly_covered_m2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m² · mean ppm {delta.data.mean_ppm_delta >= 0 ? "+" : ""}{delta.data.mean_ppm_delta.toFixed(1)}</div>}
                </div>
              </>
            ) : <Empty title="Pick A and B in Runs" />}
          </div>
        )}
        <DockFooter>
          <button className="btn acc" disabled title="The PDF export arrives with M5 reporting">Export PDF</button>
          {runB && <a className="btn" href={`/api/coverage-runs/${runB.id}/grid.npz`}>Grid .npz</a>}
          <span className="m" style={{ fontSize: 10.5, color: "var(--color-ink-3)", marginLeft: "auto" }}>{runB ? <Tag tone="ok">kernel {runB.kernel_version}</Tag> : null}</span>
        </DockFooter>
      </Dock>
    </Shell>
  );
}

function DRow({ label, a, b, badUp = false }: { label: string; a: number; b: number; badUp?: boolean }) {
  const d = b - a;
  const good = badUp ? d <= 0 : d >= 0;
  return (
    <div className="row" style={{ justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid var(--color-line)", fontSize: 12 }}>
      <span style={{ flex: 1 }}>{label}</span>
      <span className="m" style={{ width: 56, textAlign: "right" }}>{a.toFixed(1)}%</span>
      <span className="m" style={{ width: 56, textAlign: "right" }}>{b.toFixed(1)}%</span>
      <span className="m" style={{ width: 70, textAlign: "right", color: good ? "var(--color-ok)" : "var(--color-bad)", fontWeight: 500 }}>{d >= 0 ? "+" : ""}{d.toFixed(1)} pp</span>
    </div>
  );
}
