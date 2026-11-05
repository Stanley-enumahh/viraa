"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { ErrorNotice, Field } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const EMPTY_FORM = { full_name: "", username: "", email: "", password: "" };

export default function RegisterPage() {
  const { register } = useAuth();
  const [form, setForm] = useState(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function bind(name: keyof typeof EMPTY_FORM) {
    return {
      value: form[name],
      errors: fieldErrors[name],
      onChange: (event: { target: { value: string } }) => setForm({ ...form, [name]: event.target.value }),
    };
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setFieldErrors({});
    try {
      await register(form);
    } catch (caught) {
      if (caught instanceof ApiError && Object.keys(caught.fields).length) {
        setFieldErrors(caught.fields);
      } else {
        setError(caught instanceof ApiError ? caught.message : "Something went wrong. Please try again.");
      }
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <ErrorNotice message={error} />}
      <Field id="full_name" label="Full name" autoComplete="name" required {...bind("full_name")} />
      <Field
        id="username"
        label="Username"
        autoComplete="username"
        required
        hint="This is the name friends say to send you money."
        {...bind("username")}
      />
      <Field id="email" label="Email" type="email" autoComplete="email" required {...bind("email")} />
      <Field
        id="password"
        label="Password"
        type="password"
        autoComplete="new-password"
        required
        hint="At least 8 characters."
        {...bind("password")}
      />
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-accent px-4 py-3 font-semibold text-on-accent disabled:opacity-60"
      >
        {submitting ? "Creating your account…" : "Create account"}
      </button>
      <p className="text-center text-sm text-ink-2">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-ink underline underline-offset-4">
          Log in
        </Link>
      </p>
    </form>
  );
}
