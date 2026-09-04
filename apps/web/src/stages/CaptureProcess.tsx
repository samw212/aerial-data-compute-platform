/* Capture and Process stages. The viewport and dock frame are in place; the
 * footprint map, QA report and ODM console land with M6 and M7. */

import { Shell } from "../app/Shell";
import { Dock, DockFooter, DockHeader, DockTabs, Empty, Hud, Tag } from "../components/ui";
import { MapView } from "../map/MapView";
import { STATUS_TONE, useStageContext } from "./useStageContext";

export function CaptureStage() {
  const ctx = useStageContext("Capture");
  const { venue, survey } = ctx;
  const qa = survey?.capture_qa;
  const center: [number, number] = venue?.centroid_lon != null ? [venue.centroid_lon, venue.centroid_lat!] : [114.17, 22.32];
  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${survey?.name ?? "…"}`} stages={ctx.links} status={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>}>
      <MapView center={center} zoom={17} />
      <Hud lines={["Image footprints, the flight line and the gallery arrive with capture ingest (M6)."]} />
      <Dock>
        <DockHeader eyebrow="Capture" title={survey?.name ?? "…"} tag={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>} meta={survey ? `${survey.flown_at ?? "not flown"} · ${survey.platform ?? "—"} · ${survey.georef}` : undefined} />
        <DockTabs tabs={["QA", "Ground control", "Upload"]} active="QA" onPick={() => undefined} />
        {qa ? (
          <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8 }}>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Images</div><div className="m" style={{ fontSize: 17 }}>{qa.image_count}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Nadir / obl.</div><div className="m" style={{ fontSize: 17 }}>{qa.nadir_count}/{qa.oblique_count}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>RTK</div><div className="m" style={{ fontSize: 17 }}>{Math.round(qa.rtk_fraction * 100)}%</div></div>
            </div>
            {qa.blocking.length ? <div className="lbl" style={{ color: "var(--color-bad)" }}>Blocking</div> : <Tag tone="ok">no blocking items</Tag>}
            {qa.blocking.map((b, i) => <div key={i} className="row" style={{ alignItems: "flex-start" }}><Tag tone="bad">block</Tag><span style={{ fontSize: 12 }}>{b}</span></div>)}
            {qa.warnings.map((w, i) => <div key={i} className="row" style={{ alignItems: "flex-start" }}><Tag tone="warn">warn</Tag><span style={{ fontSize: 12 }}>{w}</span></div>)}
          </div>
        ) : <Empty title="No capture QA yet" hint="Upload a flight to produce it." />}
        <DockFooter><button className="btn" disabled>Upload…</button><button className="btn acc" disabled={!!qa?.blocking.length || survey?.status === "complete"}>Process →</button></DockFooter>
      </Dock>
    </Shell>
  );
}

export function ProcessStage() {
  const ctx = useStageContext("Process");
  const { venue, survey } = ctx;
  const acc = survey?.accuracy;
  const center: [number, number] = venue?.centroid_lon != null ? [venue.centroid_lon, venue.centroid_lat!] : [114.17, 22.32];
  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${survey?.name ?? "…"}`} stages={ctx.links} status={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>}>
      <MapView center={center} zoom={17} />
      <Hud lines={["Solved shots, the ODM console and the acceptance gates arrive with reconstruction (M7)."]} />
      <Dock>
        <DockHeader eyebrow="Process" title={survey?.name ?? "…"} tag={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status}</Tag>} meta={survey ? `engine ${survey.engine ?? "—"}` : undefined} />
        <DockTabs tabs={["Stages", "Gates", "Assets"]} active="Gates" onPick={() => undefined} />
        {acc ? (
          <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="lbl">Accuracy report</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8 }}>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>GSD</div><div className="m" style={{ fontSize: 16 }}>{acc.gsd_m != null ? `${(acc.gsd_m * 100).toFixed(1)} cm` : "—"}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Reproj. RMSE</div><div className="m" style={{ fontSize: 16 }}>{acc.reproj_rmse_px?.toFixed(2) ?? "—"} px</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Registered</div><div className="m" style={{ fontSize: 16 }}>{acc.registered_images}/{acc.total_images}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Check-pt RMSE <span style={{ color: "var(--color-ok)" }}>honest</span></div><div className="m" style={{ fontSize: 16 }}>{acc.check_rmse_h_m != null ? `${(acc.check_rmse_h_m * 100).toFixed(1)} H · ${((acc.check_rmse_v_m ?? 0) * 100).toFixed(1)} V cm` : "none"}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Control RMSE <span style={{ color: "var(--color-warn)" }}>optimistic</span></div><div className="m" style={{ fontSize: 16, color: "var(--color-ink-2)" }}>{acc.gcp_rmse_h_m != null ? `${(acc.gcp_rmse_h_m * 100).toFixed(1)} H · ${((acc.gcp_rmse_v_m ?? 0) * 100).toFixed(1)} V cm` : "—"}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Scale error</div><div className="m" style={{ fontSize: 16 }}>{acc.scale_error_pct != null ? `${acc.scale_error_pct >= 0 ? "+" : ""}${acc.scale_error_pct.toFixed(2)}%` : "—"}</div></div>
            </div>
          </div>
        ) : <Empty title="Not processed" hint="The processing node and console arrive with M7." />}
        <DockFooter><button className="btn" disabled>Restart with options…</button></DockFooter>
      </Dock>
    </Shell>
  );
}
