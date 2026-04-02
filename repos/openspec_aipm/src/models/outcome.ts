// Outcome types -- what happened after an agent ran
export enum OutcomeStatus {
  SUCCESS = 'success',
  PARTIAL = 'partial',
  NO_CHANGE = 'no_change',
  FAILED = 'failed',
}

export interface Outcome {
  status: OutcomeStatus;
  /** Summary line for dashboards */
  summary: string;
  /** Exit code from the agent process */
  exitCode: number;
  /** Files modified */
  filesChanged: number;
  /** Test counts [before_passing, before_total, after_passing, after_total] */
  testsBefore: [number, number];
  testsAfter: [number, number];
  /** Whether the agent committed */
  committed: boolean;
  /** Trust violations detected */
  trustViolations: string[];
}

export enum Strategy {
  FRESH = 'fresh',
  RETRY = 'retry',
  SIMPLIFY = 'simplify',
  DIFFERENT_APPROACH = 'different_approach',
}
