"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, getDashboardHome } from "@/lib/auth";

export default function DashboardPage() {
  const router = useRouter();

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        router.replace(user ? getDashboardHome(user.role) : "/login");
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  return (
    <div className="dashboard-loading">
      <span className="dashboard-spinner" />
      <p>Đang mở không gian làm việc...</p>
    </div>
  );
}
