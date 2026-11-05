"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth";

export default function Home() {
  const { user, checking } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!checking) router.replace(user ? "/dashboard" : "/login");
  }, [user, checking, router]);

  return null;
}
