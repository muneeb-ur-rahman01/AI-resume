import { z } from "zod";

// Client-side schemas are for usability only; the API validates everything independently.
export const passwordSchema = z
  .string()
  .min(12, "Use at least 12 characters.")
  .max(128, "Use at most 128 characters.");

export const registerSchema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(200),
  email: z.string().trim().email("Enter a valid email address."),
  password: passwordSchema,
  role: z.enum(["candidate", "employer"]),
  ai_processing_consent: z.boolean(),
});
export type RegisterValues = z.infer<typeof registerSchema>;

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const resetSchema = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords do not match.", path: ["confirm"] });

const optionalNumber = z.preprocess((v) => (v === "" || v == null || Number.isNaN(v) ? null : Number(v)), z.number().nonnegative().nullable());

export const jobSchema = z
  .object({
    title: z.string().trim().min(2, "Enter a title.").max(200),
    department: z.string().max(120).optional(),
    description: z.string().trim().min(20, "Describe the role (20+ characters).").max(20000),
    required_skills: z.string(),
    preferred_skills: z.string(),
    min_experience_years: optionalNumber,
    max_experience_years: optionalNumber,
    employment_type: z.enum(["full_time", "part_time", "contract", "internship", "temporary"]),
    work_arrangement: z.enum(["onsite", "hybrid", "remote"]),
    location_city: z.string().max(120).optional(),
    location_country: z.string().trim().toUpperCase().regex(/^([A-Z]{2})?$/, "Use a 2-letter country code.").optional(),
    salary_min: optionalNumber,
    salary_max: optionalNumber,
    salary_currency: z.string().trim().toUpperCase().regex(/^([A-Z]{3})?$/, "Use a 3-letter currency code.").optional(),
    application_deadline: z.string().optional(),
    external_apply_url: z.union([z.literal(""), z.string().url("Enter a full URL.")]).optional(),
  })
  .refine((v) => v.salary_min == null || v.salary_max == null || v.salary_min <= v.salary_max, {
    message: "Minimum salary must not exceed the maximum.", path: ["salary_max"],
  })
  .refine((v) => (v.salary_min == null && v.salary_max == null) || !!v.salary_currency, {
    message: "Currency is required with a salary.", path: ["salary_currency"],
  })
  .refine((v) => v.work_arrangement === "remote" || !!v.location_country, {
    message: "Country is required for onsite and hybrid roles.", path: ["location_country"],
  });
export type JobValues = z.input<typeof jobSchema>;

export const splitList = (s: string) =>
  s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
