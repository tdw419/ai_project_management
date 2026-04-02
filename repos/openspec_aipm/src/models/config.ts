// Project configuration -- mirrors AIPM v2 config.yaml but in TS
export interface ProjectConfig {
  name: string;
  path: string;
  language: string;
  testCommand: string;
  protectedFiles: string[];
  /** Max concurrent agents for this project */
  maxParallel: number;
  /** Whether to use openspec-driven or issue-driven mode */
  specDriven: boolean;
}

/** Global AIPM configuration */
export interface AipmConfig {
  /** Interval in seconds between loop cycles */
  intervalSeconds: number;
  /** Max agents running across all projects */
  maxGlobalParallel: number;
  /** Model to use for cloud routing */
  cloudModel: string;
  /** Model to use for local routing */
  localModel: string;
  /** Projects to manage */
  projects: ProjectConfig[];
  /** Path to openspec binary (auto-detected if not set) */
  openspecBin?: string;
  /** Path to hermes binary (auto-detected if not set) */
  hermesBin?: string;
  /** Data directory for prompt_log, state, etc */
  dataDir: string;
}
