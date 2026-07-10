export type FileStatus = "Idea" | "In Progress" | "Needs Work" | "Ready" | "Reference" | "Archived";

export type AssetTag = {
  label: string;
  ai_suggested: boolean;
  color?: string | null;
};

export type AudioMetadata = {
  duration_seconds: number;
  bpm_estimate?: number | null;
  sample_rate?: number | null;
  peak_amplitude?: number | null;
  peak_db?: number | null;
  rms_amplitude?: number | null;
  rms_db?: number | null;
  spectral_centroid_mean?: number | null;
  energy_series: number[];
  spectral_centroid_series: number[];
  beat_positions: number[];
  codec?: string | null;
  bitrate?: number | null;
  key_estimate?: string | null;
};

export type MidiMetadata = {
  duration_seconds: number;
  note_count: number;
  tempo_bpm?: number | null;
  pitch_min?: number | null;
  pitch_max?: number | null;
  velocity_min?: number | null;
  velocity_max?: number | null;
  instrument_names: string[];
  pitch_distribution: Record<string, number>;
  musical_summary: string;
  key_estimate?: string | null;
};

export type SessionAsset = {
  id: string;
  file_name: string;
  kind: "audio" | "midi" | "note" | "reference" | "export";
  display_type: string;
  project_name: string;
  stored_path?: string | null;
  media_url?: string | null;
  status: FileStatus;
  tags: AssetTag[];
  date_added?: string | null;
  last_analyzed?: string | null;
  note: string;
  bpm?: number | null;
  key?: string | null;
  duration?: number | null;
  audio?: AudioMetadata;
  midi?: MidiMetadata;
  text?: { text: string; word_count: number; action_items: string[] };
};

export type TaskStatus = "To do" | "In progress" | "Almost done" | "Done";

export type ProjectTask = {
  id: string;
  project_name: string;
  description: string;
  source_file: string;
  status: TaskStatus;
};

export type HealthCheck = { label: string; ok: boolean };

export type ProjectHealth = {
  score: number;
  checks: HealthCheck[];
  suggestions: string[];
};

export type ProjectSummary = {
  project_name: string;
  asset_count: number;
  audio_count: number;
  midi_count: number;
  note_count: number;
  tasks: ProjectTask[];
  progress: number;
  health: ProjectHealth;
  artwork?: string | null;
};

export type TokenUsage = { prompt: number | null; completion: number | null; total: number | null } | null;

export type QualityReport = {
  confidence: "low" | "medium" | "high";
  grounded: boolean;
  hallucination_risk: string;
  sources_retrieved: number;
  files_cited: number;
  checks: { label: string; ok: boolean }[];
  engine: string;
  mode: string;
  model: string;
  prompt_version: string;
  temperature: number | null;
  knowledge_source: string;
  token_usage: TokenUsage;
  retrieval_ms: number;
  processing_ms: number;
  generated_at: string;
};

export type PipelineStage = {
  id: string;
  title: string;
  tech: string;
  state: "active" | "available" | "fallback";
  detail: string;
};

export type PipelineResponse = {
  engine: { mode: string; model: string; endpoint: string };
  vector_search: boolean;
  prompt_version: string;
  stages: PipelineStage[];
};

export type LibraryResponse = {
  assets: SessionAsset[];
  projects: ProjectSummary[];
  smartCollections: Record<string, string[]>;
};
