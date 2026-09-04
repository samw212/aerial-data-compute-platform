/* TanStack Query hooks over the API. Keys are the URL paths, so invalidation
 * after a mutation is a prefix match. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { CoverageRun, Facility, Scenario, Structure, Survey, User, Venue, VenueSummary, MountPoint, CameraSpec, Tent } from "./contracts";

export interface AppConfig {
  version: string;
  kernel_version: string;
  maps: { provider: string; key: string | null };
  default_srid: number;
}

export const useConfig = () => useQuery({ queryKey: ["/api/config"], queryFn: () => api.get<AppConfig>("/api/config"), staleTime: Infinity });
export const useMe = () => useQuery({ queryKey: ["/api/auth/me"], queryFn: () => api.get<User>("/api/auth/me"), retry: false, staleTime: 60_000 });

export const usePortfolio = (orgId?: string) =>
  useQuery({ queryKey: ["/api/orgs", orgId, "venues"], queryFn: () => api.get<VenueSummary[]>(`/api/orgs/${orgId}/venues`), enabled: !!orgId });

export const useVenue = (id?: string) => useQuery({ queryKey: ["/api/venues", id], queryFn: () => api.get<Venue>(`/api/venues/${id}`), enabled: !!id });
export const useFacilities = (venueId?: string) =>
  useQuery({ queryKey: ["/api/venues", venueId, "facilities"], queryFn: () => api.get<Facility[]>(`/api/venues/${venueId}/facilities`), enabled: !!venueId });
export const useSurveys = (venueId?: string) =>
  useQuery({ queryKey: ["/api/venues", venueId, "surveys"], queryFn: () => api.get<Survey[]>(`/api/venues/${venueId}/surveys`), enabled: !!venueId });
export const useSurvey = (id?: string) => useQuery({ queryKey: ["/api/surveys", id], queryFn: () => api.get<Survey>(`/api/surveys/${id}`), enabled: !!id });
export const useScenarios = (venueId?: string) =>
  useQuery({ queryKey: ["/api/venues", venueId, "scenarios"], queryFn: () => api.get<Scenario[]>(`/api/venues/${venueId}/scenarios`), enabled: !!venueId });
export const useScenario = (id?: string) => useQuery({ queryKey: ["/api/scenarios", id], queryFn: () => api.get<Scenario>(`/api/scenarios/${id}`), enabled: !!id });
export const useMountPoints = (venueId?: string) =>
  useQuery({ queryKey: ["/api/venues", venueId, "mount-points"], queryFn: () => api.get<MountPoint[]>(`/api/venues/${venueId}/mount-points`), enabled: !!venueId });

export interface StructurePage {
  items: Structure[];
  next_cursor: string | null;
}
export const useStructures = (surveyId?: string) =>
  useQuery({
    queryKey: ["/api/surveys", surveyId, "structures"],
    queryFn: async () => {
      const out: Structure[] = [];
      let cursor: string | null = null;
      do {
        const page: StructurePage = await api.get<StructurePage>(`/api/surveys/${surveyId}/structures?limit=1000${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
        out.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return out;
    },
    enabled: !!surveyId,
  });

export const useRuns = (scenarioId?: string) =>
  useQuery({ queryKey: ["/api/scenarios", scenarioId, "coverage-runs"], queryFn: () => api.get<CoverageRun[]>(`/api/scenarios/${scenarioId}/coverage-runs`), enabled: !!scenarioId });

export interface SceneOut {
  cameras: CameraSpec[];
  occluders: { id: string; owner_id: string | null; porosity: number; prim: unknown }[];
  grid: { x_min: number; x_max: number; z_min: number; z_max: number; spacing: number; mask_rle: number[] };
  terrain_uri: string | null;
  kernel_version: string;
}
export const useScene = (scenarioId?: string, includeTents = true, includeSeasonal?: boolean, spacing = 0.5) =>
  useQuery({
    queryKey: ["/api/scenarios", scenarioId, "scene", includeTents, includeSeasonal ?? "default", spacing],
    queryFn: () => api.get<SceneOut>(`/api/scenarios/${scenarioId}/scene?include_tents=${includeTents}${includeSeasonal === undefined ? "" : `&include_seasonal=${includeSeasonal}`}&grid_spacing_m=${spacing}`),
    enabled: !!scenarioId,
  });

export function useInvalidate() {
  const qc = useQueryClient();
  return (...prefix: unknown[]) => qc.invalidateQueries({ queryKey: prefix });
}

export const usePatchStructure = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Structure> & { reject_reason?: string } }) => api.patch<Structure>(`/api/structures/${id}`, body),
    onSuccess: (s) => inv("/api/surveys", s.survey_id, "structures"),
  });
};

export const usePatchCamera = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body, scenarioId }: { id: string; body: Partial<CameraSpec>; scenarioId: string }) => api.patch<CameraSpec>(`/api/cameras/${id}`, body).then((c) => ({ c, scenarioId })),
    onSuccess: ({ scenarioId }) => inv("/api/scenarios", scenarioId),
  });
};

export const useRunCoverage = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ scenarioId, body }: { scenarioId: string; body: Record<string, unknown> }) => api.post<CoverageRun>(`/api/scenarios/${scenarioId}/coverage`, body),
    onSuccess: (run) => inv("/api/scenarios", run.scenario_id, "coverage-runs"),
  });
};

export type { Tent };

/* --- Source imagery (M6 capture ingest) ---------------------------------- */

export interface SourceImageRow {
  id: string;
  filename: string;
  width: number;
  height: number;
  state: string;
  captured_at: string | null;
  sharpness: number | null;
  clipped_fraction: number | null;
  gimbal_pitch_deg: number | null;
  gimbal_yaw_deg: number | null;
  rtk_fixed: boolean;
  lon: number | null;
  lat: number | null;
  altitude_m: number | null;
  thumb_url: string;
}
export interface ImagePage {
  total: number;
  accepted: number;
  items: SourceImageRow[];
}

export const useSurveyImages = (surveyId?: string, limit = 400) =>
  useQuery({
    queryKey: ["/api/surveys", surveyId, "images", limit],
    queryFn: () => api.get<ImagePage>(`/api/surveys/${surveyId}/images?limit=${limit}`),
    enabled: !!surveyId,
  });

export const useImageFootprints = (surveyId?: string) =>
  useQuery({
    queryKey: ["/api/surveys", surveyId, "images", "footprints"],
    queryFn: () => api.get<GeoJSON.FeatureCollection>(`/api/surveys/${surveyId}/images/footprints`),
    enabled: !!surveyId,
  });
