"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { ErrorNotice, Field } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(email, password);
    } catch (caught) {
      const message = caught instanceof ApiError ? caught.message : "Something went wrong. Please try again.";
      setError(caught instanceof ApiError && caught.status === 401 ? "That email or password isn't right." : message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <ErrorNotice message={error} />}
      <Field
        id="email"
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <Field
        id="password"
        label="Password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-accent px-4 py-3 font-semibold text-on-accent disabled:opacity-60"
      >
        {submitting ? "Logging in…" : "Log in"}
      </button>
      <p className="text-center text-sm text-ink-2">
        New to Vira?{" "}
        <Link href="/register" className="font-medium text-ink underline underline-offset-4">
          Create an account
        </Link>
      </p>
    </form>
  );
}
