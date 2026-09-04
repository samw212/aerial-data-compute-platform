/* What every stage needs: the venue, the survey and/or scenario from the URL,
 * and the stepper links between stages. */

import { useParams } from "react-router-dom";
import { useScenario, useScenarios, useSurvey, useSurveys, useVenue } from "../api/queries";
import type { StageLink } from "../app/Shell";

export function useStageContext(current: StageLink["stage"]) {
  const { venueId, surveyId, scenarioId } = useParams();
  const venue = useVenue(venueId);
  const surveys = useSurveys(venueId);
  const scenarios = useScenarios(venueId);
  const scenario = useScenario(scenarioId);
  const survey = useSurvey(surveyId ?? scenario.data?.base_survey_id);
  const s = survey.data;
  const effSurveyId = s?.id;
  const firstScenario = scenarios.data?.find((x) => x.base_survey_id === effSurveyId) ?? scenarios.data?.[0];
  const effScenarioId = scenarioId ?? firstScenario?.id;
  const complete = s?.status === "complete";
  const base = `/venues/${venueId}`;
  const links: StageLink[] = [
    { stage: "Capture", to: effSurveyId ? `${base}/surveys/${effSurveyId}/capture` : undefined, state: current === "Capture" ? "current" : s ? "done" : "idle" },
    { stage: "Process", to: effSurveyId ? `${base}/surveys/${effSurveyId}/process` : undefined, state: current === "Process" ? "current" : complete ? "done" : s?.status === "qa_review" || s?.status === "draft" ? "locked" : "idle", note: s?.status === "qa_review" ? "qa" : s?.status === "draft" ? "draft" : undefined },
    { stage: "Model", to: effSurveyId ? `${base}/surveys/${effSurveyId}/model` : undefined, state: current === "Model" ? "current" : complete ? "done" : "locked", note: complete ? undefined : "after processing" },
    { stage: "Plan", to: effScenarioId ? `${base}/scenarios/${effScenarioId}/plan` : undefined, state: current === "Plan" ? "current" : effScenarioId && complete ? (current === "Report" ? "done" : "idle") : "locked", note: effScenarioId ? undefined : "no scenario" },
    { stage: "Report", to: effScenarioId ? `${base}/scenarios/${effScenarioId}/report` : undefined, state: current === "Report" ? "current" : effScenarioId && complete ? "idle" : "locked" },
  ];
  return { venueId, surveyId: effSurveyId, scenarioId: effScenarioId, venue: venue.data, survey: s, scenario: scenario.data, surveys: surveys.data ?? [], scenarios: scenarios.data ?? [], links };
}

export const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "acc" | "mute"> = { complete: "ok", qa_review: "warn", failed: "bad", reconstructing: "acc", processing: "acc", extracting: "acc", queued: "acc", ingesting: "acc", draft: "mute" };
