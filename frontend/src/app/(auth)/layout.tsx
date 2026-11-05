"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { user, checking } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!checking && user) router.replace("/dashboard");
  }, [user, checking, router]);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-8">
        <Logo />
        <p className="mt-6 text-3xl font-semibold tracking-tight text-balance">Say it. Check it. Approve it.</p>
        <p className="mt-2 text-ink-2">Your crypto wallet, by voice. All funds and prices here are simulated.</p>
      </div>
      {children}
    </main>
  );
}
