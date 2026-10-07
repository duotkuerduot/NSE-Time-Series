// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


export type ApiVersion = "1"
export type ReleaseId = string
/**
 * ISO 8601 with offset, e.g. ...Z
 */
export type GeneratedAt = string
export type LatestSession = string
export type NextSession = string
/**
 * When the next release is due; past this time the frontend shows the stale banner
 */
export type StaleAfter = string
export type Status1 = ("succeeded" | "failed" | "running" | "data_not_yet_available" | "quarantined" | "skipped")
export type FinishedAt = (string | null)
export type PrimarySource = (string | null)
export type FallbackUsed = boolean
export type Dq = ("passed" | "held" | "failed" | "not_run")
export type ModelId = string
/**
 * Display name, e.g. 'LightGBM' or 'No-change baseline'
 */
export type Label = string
export type Version = string
export type Code = string
export type Message = string
export type Severity = ("info" | "warning")
export type Notices = Notice[]

/**
 * Mutable pointer to the current release. Cached for 60 seconds (22.2).
 */
export interface Status {
api_version: ApiVersion
release_id: ReleaseId
generated_at: GeneratedAt
latest_session: LatestSession
next_session: NextSession
stale_after: StaleAfter
pipeline: PipelineStatus
champion: (ModelRef | null)
notices: Notices
}
export interface PipelineStatus {
status: Status1
finished_at: FinishedAt
primary_source: PrimarySource
fallback_used: FallbackUsed
dq: Dq
}
export interface ModelRef {
model_id: ModelId
label: Label
version: Version
}
export interface Notice {
code: Code
message: Message
severity: Severity
}
