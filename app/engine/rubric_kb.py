"""
Owner: Member B

Hand-authored rubric knowledge base for retrieval-augmented scoring
(OBJECTIVE 2 RAG deliverable).

Each snippet describes what a strong or weak answer sounds like for one
competency category, phrased in natural language so that embedding-based
similarity can match snippets to a *specific job description* — a backend
JD retrieves different guidance than a data-analyst JD, even for the same
question category. This is what rag.py retrieves from at scoring time;
it replaces the old fixed per-category criteria blocks as the primary
rubric source (which is kept as a fallback).

Authored by hand on purpose: small, reviewable, no training data needed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RubricSnippet:
    category: str      # one of the competency categories below
    level: str         # "strong" | "weak" | "neutral"
    text: str          # what to look for in an answer


CATEGORIES = ("behavioral", "technical", "dsa", "system design", "communication")

RUBRIC_KB = [
    # ---------------- behavioral ----------------
    RubricSnippet("behavioral", "strong",
                  "Strong behavioral answers open with a specific past situation, name the "
                  "candidate's own role and actions, and end with a concrete measurable outcome."),
    RubricSnippet("behavioral", "strong",
                  "Ownership shows when the candidate says what THEY did and what they would do "
                  "differently, rather than describing only what the team did."),
    RubricSnippet("behavioral", "strong",
                  "Good teamwork answers describe resolving a disagreement by listening, "
                  "compromising, and communicating clearly with teammates or stakeholders."),
    RubricSnippet("behavioral", "strong",
                  "Reflection is present when the candidate states a lesson learned and how it "
                  "changed their later behavior."),
    RubricSnippet("behavioral", "weak",
                  "Weak answers stay hypothetical ('I would...'), never cite a real example, "
                  "or give a vague story with no outcome and no personal role."),
    RubricSnippet("behavioral", "weak",
                  "Blaming others, refusing any responsibility, or claiming zero conflicts ever "
                  "signals low self-awareness and weak ownership."),
    RubricSnippet("behavioral", "neutral",
                  "Relevant for customer-facing roles: look for empathy, de-escalation of "
                  "conflict, and follow-up commitments with clients or users."),
    RubricSnippet("behavioral", "neutral",
                  "For leadership-track jobs, expect initiative examples: proposing improvements, "
                  "mentoring juniors, or driving a decision without being asked."),
    RubricSnippet("behavioral", "neutral",
                  "Motivation answers should connect the role to the candidate's stated career "
                  "goals and interests rather than generic praise of the company."),
    RubricSnippet("behavioral", "neutral",
                  "Integrity signals: admitting mistakes early, escalating blockers honestly, "
                  "and respecting confidentiality."),

    # ---------------- technical ----------------
    RubricSnippet("technical", "strong",
                  "Strong technical answers state the correct concept precisely, then show depth: "
                  "why it works, what its limits are, and which alternatives were rejected."),
    RubricSnippet("technical", "strong",
                  "Depth appears as discussion of trade-offs - performance versus readability, "
                  "consistency versus availability, build versus buy - with a justified choice."),
    RubricSnippet("technical", "strong",
                  "Problem-solving is visible when the candidate decomposes the problem, states "
                  "assumptions, and reasons step by step toward a solution."),
    RubricSnippet("technical", "strong",
                  "Concrete experience signals: naming real tools, versions, bugs hit, or metrics "
                  "improved while applying the technology in production or projects."),
    RubricSnippet("technical", "weak",
                  "Weak answers recite textbook definitions without application, contradict "
                  "themselves on core concepts, or cannot explain anything beyond buzzwords."),
    RubricSnippet("technical", "weak",
                  "Red flags: confidently wrong claims about fundamentals (e.g. 'SQL joins are "
                  "always faster than nested loops') with no hedging or verification instinct."),
    RubricSnippet("technical", "neutral",
                  "For backend roles, expect comfort with databases, REST or GraphQL APIs, "
                  "authentication, caching layers, and message queues."),
    RubricSnippet("technical", "neutral",
                  "For frontend roles, expect component state management, browser rendering "
                  "behavior, accessibility basics, and API integration patterns."),
    RubricSnippet("technical", "neutral",
                  "For data roles, expect SQL fluency, data-cleaning judgment, statistics "
                  "fundamentals, and awareness of bias in datasets."),
    RubricSnippet("technical", "neutral",
                  "For DevOps-flavored jobs, look for CI/CD pipelines, containerization with "
                  "Docker, infrastructure-as-code, and incident debugging stories."),
    RubricSnippet("technical", "neutral",
                  "Testing maturity: strong candidates mention unit tests, edge-case coverage, "
                  "and how they verify fixes rather than shipping untested code."),

    # ---------------- dsa ----------------
    RubricSnippet("dsa", "strong",
                  "Strong algorithm answers start from brute force, analyze its time complexity, "
                  "then improve it with a named optimal approach such as hashing, two pointers, "
                  "dynamic programming, or binary search."),
    RubricSnippet("dsa", "strong",
                  "Complexity analysis is explicit: the candidate states big-O time AND space for "
                  "their final solution and justifies both."),
    RubricSnippet("dsa", "strong",
                  "Edge cases are enumerated unprompted: empty input, single element, duplicates, "
                  "negative numbers, overflow, or sorted versus unsorted input."),
    RubricSnippet("dsa", "strong",
                  "Correctness reasoning walks through a small worked example, tracing how the "
                  "data structure changes step by step."),
    RubricSnippet("dsa", "weak",
                  "Weak answers jump straight to code with no complexity discussion, choose a "
                  "data structure arbitrarily, or claim O(1) for operations that are O(n)."),
    RubricSnippet("dsa", "weak",
                  "Memorized-pattern answers collapse under one follow-up: the candidate cannot "
                  "explain why their approach works or adapt it when a constraint changes."),
    RubricSnippet("dsa", "neutral",
                  "For performance-sensitive roles, expect attention to constant factors, cache "
                  "behavior, and avoiding unnecessary copies."),
    RubricSnippet("dsa", "neutral",
                  "For large-scale data roles, expect streaming or external-memory thinking when "
                  "the input does not fit in RAM."),
    RubricSnippet("dsa", "neutral",
                  "Recursion comfort: clear base cases, awareness of stack depth, and ability to "
                  "convert recursive solutions to iterative ones."),

    # ---------------- system design ----------------
    RubricSnippet("system design", "strong",
                  "Strong design answers clarify requirements and scale assumptions first "
                  "(users, QPS, data size), then propose components with responsibilities."),
    RubricSnippet("system design", "strong",
                  "Scalability reasoning names bottlenecks - database reads, hot partitions, "
                  "fan-out - and mitigations like caching, sharding, replication, or queues."),
    RubricSnippet("system design", "strong",
                  "Trade-off discussion compares options explicitly (SQL vs NoSQL, push vs pull, "
                  "strong vs eventual consistency) and commits to one with justification."),
    RubricSnippet("system design", "strong",
                  "Reliability thinking includes failure modes: what happens when a service dies, "
                  "retries, timeouts, idempotency, and graceful degradation."),
    RubricSnippet("system design", "weak",
                  "Weak answers draw a single monolithic box labeled 'server' and 'database', "
                  "name trendy technologies without justifying them, or ignore scale entirely."),
    RubricSnippet("system design", "weak",
                  "No failure analysis and no data-growth discussion indicates shallow design "
                  "experience even if the happy path is correct."),
    RubricSnippet("system design", "neutral",
                  "For microservice-heavy organizations, expect service boundaries, API contracts, "
                  "and inter-service auth discussion."),
    RubricSnippet("system design", "neutral",
                  "For data-platform roles, expect batch versus stream pipelines, warehouse "
                  "modeling, and backfill strategy."),
    RubricSnippet("system design", "neutral",
                  "Security-aware designs mention authentication flows, rate limiting, and "
                  "least-privilege access between components."),
    RubricSnippet("system design", "neutral",
                  "Cost consciousness: discussing managed services vs self-hosted and the operational "
                  "burden of each choice."),

    # ---------------- communication ----------------
    RubricSnippet("communication", "strong",
                  "Clear communicators structure answers with signposts ('there are three parts'), "
                  "finish sentences, and stay on topic without tangents."),
    RubricSnippet("communication", "strong",
                  "Confidence shows as steady pacing, direct claims owned by the speaker, and "
                  "calm handling of uncertainty ('I would verify that rather than guess')."),
    RubricSnippet("communication", "strong",
                  "Concise answers carry information density: every sentence adds content, filler "
                  "words are rare, and the point arrives within the first two sentences."),
    RubricSnippet("communication", "strong",
                  "Adapting explanation to audience - offering an analogy for non-technical "
                  "listeners - demonstrates genuine understanding, not jargon recall."),
    RubricSnippet("communication", "weak",
                  "Rambling answers loop back on themselves, trail off mid-thought, or bury the "
                  "point under heavy filler ('um', 'basically', 'you know')."),
    RubricSnippet("communication", "weak",
                  "Jargon-dropping without explanation, interrupting the question, or answering "
                  "a different question than the one asked all signal poor listening."),
    RubricSnippet("communication", "neutral",
                  "For client-facing roles, prioritize warmth, plain-language summaries, and "
                  "setting expectations about next steps."),
    RubricSnippet("communication", "neutral",
                  "For remote-first teams, look for crisp written-style verbal summaries and "
                  "explicit confirmation of shared understanding."),
    RubricSnippet("communication", "neutral",
                  "Handling pushback gracefully - restating the interviewer's concern before "
                  "responding - indicates collaborative communication."),
]
