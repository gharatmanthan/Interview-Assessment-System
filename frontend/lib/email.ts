/**
 * Canonical email validation + normalization (frontend).
 * Mirrors app/core/validation.py exactly so both sides agree.
 */

// Local part: dot-separated atoms; each atom is 1+ RFC-5322 atom chars.
const LOCAL_ATOM = "[A-Za-z0-9!#$%&'*+\\-/=?^_`{|}~]+"
const LOCAL_PART = LOCAL_ATOM + "(?:\\." + LOCAL_ATOM + ")*"

// Domain: two or more labels. Each label starts/ends with alnum, may
// contain internal hyphens, 1-63 chars.
const DOMAIN_LABEL = "[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
const DOMAIN = DOMAIN_LABEL + "(?:\\." + DOMAIN_LABEL + ")+"

export const EMAIL_RE = new RegExp("^" + LOCAL_PART + "@" + DOMAIN + "$")

export function normalizeEmail(value: string): string {
  return (value ?? "").trim().toLowerCase()
}

export function isValidEmail(value: string): boolean {
  if (typeof value !== "string") return false
  const s = value.trim()
  if (!s || s.length > 254 || /\s/.test(s) || !s.includes("@")) return false
  return EMAIL_RE.test(s)
}
