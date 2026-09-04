/* The plan-view map: MapLibre over the Hong Kong Lands Department tiles.
 * docs/FRONTEND-DESIGN.md section 5. Children add layers through the context. */

import maplibregl, { type Map as MLMap, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useUi } from "../state/ui";

const HK = "https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz";
const ATTR = '© <a href="https://portal.csdi.gov.hk/">Lands Department, HKSAR</a> · Map data from GeoData Store';

export const baseStyle: StyleSpecification = {
  version: 8,
  // Glyphs for symbol layers (labels on cameras, structures, venues). Open, keyless.
  glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
  sources: {
    basemap: { type: "raster", tiles: [`${HK}/basemap/wgs84/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 20, attribution: ATTR },
    imagery: { type: "raster", tiles: [`${HK}/imagery/wgs84/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 19, attribution: ATTR },
    labels: { type: "raster", tiles: [`${HK}/label/hk/en/wgs84/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 20 },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0e1116" } },
    { id: "basemap", type: "raster", source: "basemap", paint: { "raster-opacity": 0.85, "raster-saturation": -0.5, "raster-brightness-max": 0.7, "raster-brightness-min": 0.05, "raster-contrast": 0.05 } },
    { id: "imagery", type: "raster", source: "imagery", layout: { visibility: "none" }, paint: { "raster-opacity": 0.9, "raster-brightness-max": 0.85 } },
    { id: "labels", type: "raster", source: "labels", paint: { "raster-opacity": 0.7 } },
  ],
};

/** False once map.remove() has run: layer cleanups must not touch a dead map. */
function alive(map: MLMap | null): map is MLMap {
  return !!map && !(map as unknown as { _removed?: boolean })._removed && !!(map as unknown as { style?: unknown }).style;
}

const MapCtx = createContext<MLMap | null>(null);
export const useMap = () => useContext(MapCtx);

export function MapView({ center, zoom = 17, bounds, children, onClick, onMouseMove }: { center: [number, number]; zoom?: number; bounds?: [number, number][] | null; children?: ReactNode; onClick?: (lngLat: [number, number], e: maplibregl.MapMouseEvent) => void; onMouseMove?: (lngLat: [number, number]) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MLMap | null>(null);
  const layers = useUi((s) => s.layers);

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({ container: el.current, style: baseStyle, center, zoom, attributionControl: { compact: true }, maxPitch: 0, dragRotate: false, pitchWithRotate: false });
    m.touchZoomRotate.disableRotation();
    (window as unknown as { __adcpMap?: MLMap }).__adcpMap = m; // for e2e assertions
    m.on("load", () => setMap(m));
    return () => { setMap(null); m.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fit once to the facility (or whatever ring the stage hands in), padded for the dock.
  const fitted = useRef(false);
  useEffect(() => {
    if (!map || !bounds || !bounds.length || fitted.current) return;
    const lngs = bounds.map((p) => p[0]), lats = bounds.map((p) => p[1]);
    map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]], { padding: { top: 90, bottom: 60, left: 70, right: 430 }, duration: 0 });
    fitted.current = true;
  }, [map, bounds]);

  useEffect(() => {
    if (!map) return;
    map.setLayoutProperty("basemap", "visibility", layers.basemap ? "visible" : "none");
    map.setLayoutProperty("imagery", "visibility", layers.imagery ? "visible" : "none");
    map.setLayoutProperty("labels", "visibility", layers.labels ? "visible" : "none");
  }, [map, layers.basemap, layers.imagery, layers.labels]);

  useEffect(() => {
    if (!map || !onClick) return;
    const h = (e: maplibregl.MapMouseEvent) => onClick([e.lngLat.lng, e.lngLat.lat], e);
    map.on("click", h);
    return () => { map.off("click", h); };
  }, [map, onClick]);

  useEffect(() => {
    if (!map || !onMouseMove) return;
    const h = (e: maplibregl.MapMouseEvent) => onMouseMove([e.lngLat.lng, e.lngLat.lat]);
    map.on("mousemove", h);
    return () => { map.off("mousemove", h); };
  }, [map, onMouseMove]);

  return (
    <div ref={el} style={{ position: "absolute", inset: 0 }}>
      <MapCtx.Provider value={map}>{map ? children : null}</MapCtx.Provider>
    </div>
  );
}

/** A GeoJSON source + one or more layers, kept in sync with `data`. */
export function GeoLayer({ id, data, layers, visible = true, before }: { id: string; data: GeoJSON.FeatureCollection; layers: Omit<maplibregl.LayerSpecification, "source">[]; visible?: boolean; before?: string }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    if (!map.getSource(id)) map.addSource(id, { type: "geojson", data });
    else (map.getSource(id) as maplibregl.GeoJSONSource).setData(data);
    for (const l of layers) {
      if (!map.getLayer(l.id)) map.addLayer({ ...(l as maplibregl.LayerSpecification), source: id } as maplibregl.LayerSpecification, before && map.getLayer(before) ? before : undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, id, data]);
  useEffect(() => {
    if (!alive(map)) return;
    for (const l of layers) if (map.getLayer(l.id)) map.setLayoutProperty(l.id, "visibility", visible ? "visible" : "none");
  }, [map, layers, visible]);
  useEffect(() => () => {
    if (!alive(map)) return;
    for (const l of layers) if (map.getLayer(l.id)) map.removeLayer(l.id);
    if (map.getSource(id)) map.removeSource(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, id]);
  return null;
}

/** A raster image draped between four corners (top-left, top-right, bottom-right, bottom-left). */
export function ImageLayer({ id, url, coordinates, visible = true, opacity = 1, before }: { id: string; url: string; coordinates: [number, number][]; visible?: boolean; opacity?: number; before?: string }) {
  const map = useMap();
  useEffect(() => {
    if (!map || !url) return;
    const src = map.getSource(id) as maplibregl.ImageSource | undefined;
    if (!src) {
      map.addSource(id, { type: "image", url, coordinates: coordinates as [[number, number], [number, number], [number, number], [number, number]] });
      map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-resampling": "nearest", "raster-fade-duration": 0 } }, before && map.getLayer(before) ? before : undefined);
    } else {
      src.updateImage({ url, coordinates: coordinates as [[number, number], [number, number], [number, number], [number, number]] });
    }
  }, [map, id, url, coordinates, opacity, before]);
  useEffect(() => {
    if (!alive(map) || !map.getLayer(id)) return;
    map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    map.setPaintProperty(id, "raster-opacity", opacity);
  }, [map, id, visible, opacity]);
  useEffect(() => () => {
    if (!alive(map)) return;
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, id]);
  return null;
}
