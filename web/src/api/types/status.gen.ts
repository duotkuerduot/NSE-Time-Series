// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


export type ApiVersion = "1"
export type ContractVersion = "1.1"
export type ReleaseId = string
/**
 * ISO 8601 with offset, e.g. ...Z
 */
export type GeneratedAt = string
export type LatestSession = string
export type NextSession = string
/**
 * When the next release is due; null in local mode, where data is never late
 */
export type StaleAfter = (string | null)
export type DataMode = ("historical" | "historical+imports" | "sample")
export type Source = ("mendeley" | "local" | "sample")
export type Title = string
export type Version = (number | null)
export type FirstSession = string
export type LastSession = string
export type Licence = (string | null)
export type Citation = (string | null)
export type Doi = (string | null)
export type Url = (string | null)
export type Status1 = ("succeeded" | "failed" | "running" | "data_not_yet_available" | "quarantined" | "skipped")
export type FinishedAt = (string | null)
export type PrimarySource = ("mendeley" | "local" | "sample")
/**
 * Always false in local mode
 */
export type FallbackUsed = boolean
export type Dq = ("passed" | "held" | "failed" | "not_run")
export type ModelId = string
/**
 * Display name, e.g. 'LightGBM' or 'No-change baseline'
 */
export type Label = string
export type Version1 = string
export type Code = string
export type Message = string
export type Severity = ("info" | "warning")
export type Notices = Notice[]

/**
 * Pointer to the current release, plus run and data status.
 */
export interface Status {
api_version: ApiVersion
contract_version: ContractVersion
release_id: ReleaseId
generated_at: GeneratedAt
latest_session: LatestSession
next_session: NextSession
stale_after: StaleAfter
data_mode: DataMode
dataset: DatasetInfo
pipeline: PipelineStatus
champion: (ModelRef | null)
notices: Notices
}
/**
 * Where the data came from, for the header, footer and About page (v1.1).
 */
export interface DatasetInfo {
source: Source
title: Title
version: Version
first_session: FirstSession
last_session: LastSession
licence: Licence
citation: Citation
doi: Doi
url: Url
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
version: Version1
}
export interface Notice {
code: Code
message: Message
severity: Severity
}
