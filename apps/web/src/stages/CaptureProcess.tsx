/* Capture and Process stages.
 *
 * Capture is live: the gallery, the image footprints and the flight line come from
 * capture ingest (M6). The Process stage's solved shots and ODM console land with
 * reconstruction (M7). */

import { useMemo, useState } from "react";
import type { Venue } from "../api/contracts";
import type { SourceImageRow } from "../api/queries";
import { useFacilities, useImageFootprints, useSurveyImages } from "../api/queries";
import { Shell } from "../app/Shell";
import { Dock, DockFooter, DockHeader, DockTabs, Empty, Hud, Tag } from "../components/ui";
import { GeoLayer, MapView } from "../map/MapView";
import { localToLngLat, storageRingToLngLat } from "../geo";
import { STATUS_TONE, useStageContext } from "./useStageContext";

/** The venue map with the facility outlines: the frame every survey stage shares. */
function VenueMap({
  venueId,
  venue,
  footprints,
  selected,
}: {
  venueId?: string;
  venue?: Venue | null;
  footprints?: GeoJSON.FeatureCollection | null;
  selected?: string | null;
}) {
  const facilities = useFacilities(venueId);
  const fc = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: venue ? (facilities.data ?? []).map((f) => ({ type: "Feature", id: f.id, properties: { name: f.name }, geometry: { type: "Polygon", coordinates: [storageRingToLngLat(venue.srid, f.boundary)] } })) : [],
  }), [venue, facilities.data]);
  const mapCenter: [number, number] = venue ? localToLngLat(venue, 0, 0) : [114.17, 22.32];
  const bounds = useMemo(() => (venue && facilities.data?.[0] ? storageRingToLngLat(venue.srid, facilities.data[0].boundary) : null), [venue, facilities.data]);
  return (
    <MapView center={mapCenter} zoom={17} bounds={bounds}>
      <GeoLayer id="facilities" data={fc} layers={[{ id: "fac-line", type: "line", paint: { "line-color": "#5ee7ff", "line-width": 1.5, "line-dasharray": [4, 3], "line-opacity": 0.8 } }]} />
      {footprints && (
        <GeoLayer
          id="footprints"
          data={footprints}
          layers={[
            // Hundreds of overlapping rectangles: a low fill opacity makes the
            // overlap itself legible, since where the flight doubled back the
            // ground reads brighter.
            { id: "fp-fill", type: "fill", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#5ee7ff", "fill-opacity": 0.06 } },
            { id: "fp-line", type: "line", filter: ["==", ["geometry-type"], "Polygon"], paint: { "line-color": "#5ee7ff", "line-width": 0.5, "line-opacity": 0.45 } },
            { id: "fp-sel", type: "line", filter: ["all", ["==", ["geometry-type"], "Polygon"], ["==", ["get", "image_id"], selected ?? ""]], paint: { "line-color": "#ffd166", "line-width": 2.5 } },
            { id: "fp-track", type: "line", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#9aa4b2", "line-width": 1, "line-opacity": 0.8, "line-dasharray": [3, 2] } },
          ]}
        />
      )}
    </MapView>
  );
}

/** One frame in the contact sheet. */
function Thumb({ img, active, onPick }: { img: SourceImageRow; active: boolean; onPick: () => void }) {
  const rejected = img.state !== "accepted";
  return (
    <button
      type="button"
      onClick={onPick}
      title={`${img.filename}${rejected ? ` · ${img.state.replace("_", " ")}` : ""}`}
      style={{
        position: "relative", padding: 0, border: active ? "1.5px solid var(--color-acc)" : "1px solid var(--color-line)",
        borderRadius: 3, overflow: "hidden", background: "#0b0e13", cursor: "pointer", aspectRatio: "4 / 3",
      }}
    >
      <img
        src={img.thumb_url}
        alt={img.filename}
        loading="lazy"
        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block", opacity: rejected ? 0.35 : 1 }}
      />
      {rejected && (
        <span style={{ position: "absolute", top: 2, left: 2, fontSize: 8.5, letterSpacing: 0.4, textTransform: "uppercase", background: "var(--color-bad)", color: "#0b0e13", padding: "1px 3px", borderRadius: 2 }}>
          {img.state.replace("rejected_", "")}
        </span>
      )}
    </button>
  );
}

export function CaptureStage() {
  const ctx = useStageContext("Capture");
  const { venue, survey } = ctx;
  const qa = survey?.capture_qa;
  const images = useSurveyImages(survey?.id);
  const footprints = useImageFootprints(survey?.id);
  const [tab, setTab] = useState("Gallery");
  const [picked, setPicked] = useState<string | null>(null);

  const items = images.data?.items ?? [];
  const current = items.find((i) => i.id === picked) ?? null;
  const hasImages = items.length > 0;

  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${survey?.name ?? "…"}`} stages={ctx.links} status={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>}>
      <VenueMap venueId={ctx.venueId} venue={venue} footprints={footprints.data ?? null} selected={picked} />
      <Hud
        lines={
          hasImages
            ? [
                `${images.data?.total ?? 0} frames · ${images.data?.accepted ?? 0} accepted`,
                current ? `${current.filename}${current.altitude_m != null ? ` · ${current.altitude_m.toFixed(0)} m` : ""}` : "footprints drawn for nadir frames only",
              ]
            : ["No imagery ingested. Run `groma capture ingest <dir> --survey <id>`."]
        }
      />
      <Dock>
        <DockHeader eyebrow="Capture" title={survey?.name ?? "…"} tag={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>} meta={survey ? `${survey.flown_at ?? "not flown"} · ${survey.platform ?? "—"} · ${survey.georef}` : undefined} />
        <DockTabs tabs={["Gallery", "QA"]} active={tab} onPick={setTab} />

        {tab === "Gallery" && (
          <div className="scroll" style={{ flex: 1, padding: "10px 12px" }}>
            {images.isLoading && <Empty title="Loading frames…" />}
            {!images.isLoading && !hasImages && (
              <Empty title="No imagery yet" hint="Ingest a flight to fill the gallery and draw its footprints." />
            )}
            {hasImages && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 5 }}>
                  {items.map((img) => (
                    <Thumb key={img.id} img={img} active={img.id === picked} onPick={() => setPicked(img.id === picked ? null : img.id)} />
                  ))}
                </div>
                {current && (
                  <div style={{ marginTop: 10, borderTop: "1px solid var(--color-line)", paddingTop: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>{current.filename}</div>
                    <div className="m" style={{ fontSize: 10.5, color: "var(--color-ink-2)", marginTop: 4, lineHeight: 1.7 }}>
                      {current.width} × {current.height}
                      {current.captured_at ? ` · ${current.captured_at.replace("T", " ").slice(0, 19)}` : ""}
                      <br />
                      {current.gimbal_pitch_deg != null ? `pitch ${current.gimbal_pitch_deg.toFixed(1)}°` : "pitch —"}
                      {current.gimbal_yaw_deg != null ? ` · yaw ${current.gimbal_yaw_deg.toFixed(1)}°` : ""}
                      {current.altitude_m != null ? ` · ${current.altitude_m.toFixed(1)} m` : ""}
                      <br />
                      {current.sharpness != null ? `sharpness ${current.sharpness.toFixed(0)}` : "sharpness —"}
                      {current.clipped_fraction != null ? ` · clipped ${(current.clipped_fraction * 100).toFixed(1)}%` : ""}
                      {current.rtk_fixed ? " · RTK fixed" : ""}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {tab === "QA" && (
          qa ? (
            <div className="scroll" style={{ flex: 1, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8 }}>
                <div><div className="lbl" style={{ fontSize: 9.5 }}>Images</div><div className="m" style={{ fontSize: 17 }}>{qa.image_count}</div></div>
                <div><div className="lbl" style={{ fontSize: 9.5 }}>Nadir / obl.</div><div className="m" style={{ fontSize: 17 }}>{qa.nadir_count}/{qa.oblique_count}</div></div>
                <div><div className="lbl" style={{ fontSize: 9.5 }}>RTK</div><div className="m" style={{ fontSize: 17 }}>{Math.round(qa.rtk_fraction * 100)}%</div></div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8 }}>
                <div><div className="lbl" style={{ fontSize: 9.5 }}>GSD</div><div className="m" style={{ fontSize: 15 }}>{qa.estimated_gsd_m != null ? `${(qa.estimated_gsd_m * 100).toFixed(1)} cm` : "—"}</div></div>
                <div><div className="lbl" style={{ fontSize: 9.5 }}>Front ovl.</div><div className="m" style={{ fontSize: 15 }}>{qa.estimated_front_overlap != null ? `${Math.round(qa.estimated_front_overlap * 100)}%` : "—"}</div></div>
                <div><div className="lbl" style={{ fontSize: 9.5 }}>Side ovl.</div><div className="m" style={{ fontSize: 15 }}>{qa.estimated_side_overlap != null ? `${Math.round(qa.estimated_side_overlap * 100)}%` : "—"}</div></div>
              </div>
              {qa.blocking.length ? <div className="lbl" style={{ color: "var(--color-bad)" }}>Blocking</div> : <Tag tone="ok">no blocking items</Tag>}
              {qa.blocking.map((b, i) => <div key={i} className="row" style={{ alignItems: "flex-start" }}><Tag tone="bad">block</Tag><span style={{ fontSize: 12 }}>{b}</span></div>)}
              {qa.warnings.map((w, i) => <div key={i} className="row" style={{ alignItems: "flex-start" }}><Tag tone="warn">warn</Tag><span style={{ fontSize: 12 }}>{w}</span></div>)}
            </div>
          ) : <Empty title="No capture QA yet" hint="Ingest a flight to produce it." />
        )}

        <DockFooter><button className="btn" disabled>Upload…</button><button className="btn acc" disabled={!!qa?.blocking.length || survey?.status === "complete"}>Process →</button></DockFooter>
      </Dock>
    </Shell>
  );
}


export function ProcessStage() {
  const ctx = useStageContext("Process");
  const { venue, survey } = ctx;
  const acc = survey?.accuracy;
  return (
    <Shell crumb={`${venue?.name ?? "…"} · ${survey?.name ?? "…"}`} stages={ctx.links} status={survey && <Tag tone={STATUS_TONE[survey.status] ?? "mute"}>{survey.status.replace("_", " ")}</Tag>}>
      <VenueMap venueId={ctx.venueId} venue={venue} />
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
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Check-pt RMSE cm <span style={{ color: "var(--color-ok)" }}>honest</span></div><div className="m" style={{ fontSize: 14, whiteSpace: "nowrap" }}>{acc.check_rmse_h_m != null ? `${(acc.check_rmse_h_m * 100).toFixed(1)} H · ${((acc.check_rmse_v_m ?? 0) * 100).toFixed(1)} V` : "none"}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Control RMSE cm <span style={{ color: "var(--color-warn)" }}>optimistic</span></div><div className="m" style={{ fontSize: 14, whiteSpace: "nowrap", color: "var(--color-ink-2)" }}>{acc.gcp_rmse_h_m != null ? `${(acc.gcp_rmse_h_m * 100).toFixed(1)} H · ${((acc.gcp_rmse_v_m ?? 0) * 100).toFixed(1)} V` : "—"}</div></div>
              <div><div className="lbl" style={{ fontSize: 9.5 }}>Scale error</div><div className="m" style={{ fontSize: 16 }}>{acc.scale_error_pct != null ? `${acc.scale_error_pct >= 0 ? "+" : ""}${acc.scale_error_pct.toFixed(2)}%` : "—"}</div></div>
            </div>
          </div>
        ) : <Empty title="Not processed" hint="The processing node and console arrive with M7." />}
        <DockFooter><button className="btn" disabled>Restart with options…</button></DockFooter>
      </Dock>
    </Shell>
  );
}
