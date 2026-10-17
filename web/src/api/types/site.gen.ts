// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


export type OwnerName = string
export type Tagline = string
export type Label = string
export type Url = string
export type Links = SiteLink[]
export type Attribution = string

/**
 * Owner name and contact links from config/site.yaml, plus dataset attribution.
 */
export interface Site {
owner_name: OwnerName
tagline: Tagline
links: Links
attribution: Attribution
}
export interface SiteLink {
label: Label
url: Url
}
