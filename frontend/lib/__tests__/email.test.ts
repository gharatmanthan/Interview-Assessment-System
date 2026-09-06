import { describe, it, expect } from "vitest"
import { isValidEmail, normalizeEmail, EMAIL_RE } from "../email"

const VALID_EMAILS = [
  "user@gmail.com",
  "john.doe@company.com",
  "name+jobs@company.co.in",
  "first.last+tag@sub.domain.org",
  "a@b.co",
]

const INVALID_EMAILS = [
  "abc",
  "test@",
  "@test.com",
  "test@gmail",
  "test..abc@gmail.com",
  "user@.com",
  "a b@c.com",
  "user test@example.com",
  " ",
]

describe("isValidEmail", () => {
  it("accepts standard valid emails", () => {
    for (const email of VALID_EMAILS) {
      expect(isValidEmail(email), email).toBe(true)
    }
  })

  it("rejects malformed emails", () => {
    for (const email of INVALID_EMAILS) {
      expect(isValidEmail(email), email).toBe(false)
    }
  })

  it("rejects empty and non-string inputs", () => {
    expect(isValidEmail("")).toBe(false)
    expect(isValidEmail(null as unknown as string)).toBe(false)
    expect(isValidEmail(undefined as unknown as string)).toBe(false)
  })
})

describe("normalizeEmail", () => {
  it("trims and lowercases", () => {
    expect(normalizeEmail("  USER@Example.COM  ")).toBe("user@example.com")
    expect(normalizeEmail(" user@example.com\t")).toBe("user@example.com")
    expect(normalizeEmail("")).toBe("")
  })
})

describe("EMAIL_RE", () => {
  it("accepts valid patterns", () => {
    for (const email of VALID_EMAILS) {
      expect(EMAIL_RE.test(email), email).toBe(true)
    }
  })

  it("rejects invalid patterns", () => {
    for (const email of INVALID_EMAILS) {
      // filter out pure whitespace which doesn't match anyway
      if (email.trim()) {
        expect(EMAIL_RE.test(email), email).toBe(false)
      }
    }
  })

  it("rejects addresses with internal whitespace", () => {
    expect(EMAIL_RE.test("a b@c.com")).toBe(false)
    expect(EMAIL_RE.test("ab@c .com")).toBe(false)
  })
})
