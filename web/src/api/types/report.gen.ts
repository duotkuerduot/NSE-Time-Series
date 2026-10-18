// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


export type Profile = ("default" | "full")
export type Refit = string
export type Start = string
export type End = string
export type Source = ("mendeley" | "local" | "sample")
export type Title = string
export type Version = (number | null)
export type FirstSession = string
export type LastSession = string
export type Licence = (string | null)
export type Citation = (string | null)
export type Doi = (string | null)
export type Url = (string | null)
export type Min = number
export type Max = number
export type Median = number
export type AtLastSession = number
export type ModelId = string
export type Label = string
export type Reason = string
/**
 * An average absolute error, e.g. 0.0124
 */
export type Mae = number
/**
 * An average absolute error, e.g. 0.0124
 */
export type MaeNoChange = number
/**
 * 1 - MAE / MAE of the no-change guess
 */
export type Skill = number
/**
 * One-sided Diebold-Mariano p-value against no change
 */
export type DmP = (number | null)
/**
 * Share of actual closes inside the 80% range
 */
export type Coverage = (number | null)
export type DirectionAccuracy = (number | null)
export type Rows = number
export type Securities = number
export type ModelId1 = string
export type Label1 = string
export type IsChampion = boolean
/**
 * Gate id, e.g. G-SKILL (docs/methodology.md, Gates)
 */
export type Id = string
/**
 * Plain-language name shown in the app
 */
export type Name = string
export type Passed = boolean
export type Detail = string
export type Gates = ReportGate[]
export type Models = ReportModel[]
export type Sessions = number
export type Securities1 = number
export type CorrectionsApplied = number
export type RowsCorrected = number
export type DuplicatesDropped = number
export type MissingSessions = number
export type EventsExcluded = number
export type CarriedForwardRows = number

/**
 * Evaluation results for the About page.
 */
export interface Report {
profile: Profile
refit: Refit
periods: ReportPeriods
dataset: DatasetInfo
universe: ReportUniverse
champion: ReportChampion
/**
 * The champion's holdout scores
 */
headline: (ReportScores | null)
models: Models
data_audit: DataAudit
}
export interface ReportPeriods {
selection: ReportPeriod
holdout: ReportPeriod
}
export interface ReportPeriod {
start: Start
end: End
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
export interface ReportUniverse {
min: Min
max: Max
median: Median
at_last_session: AtLastSession
}
export interface ReportChampion {
model_id: ModelId
label: Label
reason: Reason
}
export interface ReportScores {
mae: Mae
mae_no_change: MaeNoChange
skill: Skill
dm_p: DmP
coverage: Coverage
direction_accuracy: DirectionAccuracy
rows: Rows
securities: Securities
}
export interface ReportModel {
model_id: ModelId1
label: Label1
is_champion: IsChampion
selection: ReportScores
holdout: (ReportScores | null)
gates: Gates
skill_by_year: SkillByYear
}
export interface ReportGate {
id: Id
name: Name
passed: Passed
detail: Detail
}
export interface SkillByYear {
[k: string]: number
}
export interface DataAudit {
sessions: Sessions
securities: Securities1
corrections_applied: CorrectionsApplied
rows_corrected: RowsCorrected
duplicates_dropped: DuplicatesDropped
missing_sessions: MissingSessions
events_excluded: EventsExcluded
carried_forward_rows: CarriedForwardRows
}
