import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError, errorMessage } from "@/lib/api";
import { jobSchema } from "@/lib/schemas";
import { Badge, Field, Input, MatchScore } from "./ui";

describe("MatchScore", () => {
  it("exposes the score as text, not only color", () => {
    render(<MatchScore score={72} />);
    expect(screen.getByLabelText("Relevance score 72 out of 100")).toHaveTextContent("72/100");
  });
});

describe("Field", () => {
  it("wires label, error and aria attributes", () => {
    render(<Field label="Email" error="Enter a valid email address.">{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(input.getAttribute("aria-describedby")).toContain("-err");
  });
});

describe("Badge", () => {
  it("renders status text", () => {
    render(<Badge tone="success">Verified</Badge>);
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });
});

describe("errorMessage", () => {
  it("prefers password policy details and field errors", () => {
    expect(errorMessage(new ApiError(422, "validation_failed", "x", { password: ["Too short."] }))).toBe("Too short.");
    expect(errorMessage(new ApiError(422, "validation_failed", "x", { fields: [{ loc: ["body", "title"], msg: "required" }] }))).toBe("title: required");
    expect(errorMessage(new Error("boom"))).toBe("Something went wrong. Please try again.");
  });
});

describe("jobSchema", () => {
  const base = { title: "Engineer", description: "A sufficiently long description.", required_skills: "Python", preferred_skills: "", employment_type: "full_time", work_arrangement: "remote" } as const;
  it("accepts a remote job without location", () => {
    expect(jobSchema.safeParse(base).success).toBe(true);
  });
  it("rejects inverted salary ranges and missing currency", () => {
    expect(jobSchema.safeParse({ ...base, salary_min: 10, salary_max: 5, salary_currency: "USD" }).success).toBe(false);
    expect(jobSchema.safeParse({ ...base, salary_min: 10 }).success).toBe(false);
  });
  it("requires a country for onsite roles", () => {
    expect(jobSchema.safeParse({ ...base, work_arrangement: "onsite" }).success).toBe(false);
  });
});
