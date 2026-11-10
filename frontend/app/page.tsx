"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { getToken, getUser, HOME } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const user = getUser();
    router.replace(getToken() && user ? HOME[user.role] : "/login");
  }, [router]);
  return <p className="p-6 text-sm text-muted">Opening EduCrew…</p>;
}
