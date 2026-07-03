"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  createDevSession,
  DEV_AUTH_ENABLED,
  type DashboardUser,
} from "@/lib/auth";

type LoginResponse = {
  access_token: string;
  user: unknown;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const POST_LOGIN_PATH =
  process.env.NEXT_PUBLIC_POST_LOGIN_PATH ?? "/dashboard";

export function LoginForm() {
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");

    try {
      if (DEV_AUTH_ENABLED) {
        const devResponse = await fetch("/api/dev-login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        const devData = (await devResponse.json().catch(() => ({}))) as {
          detail?: string;
          user?: DashboardUser;
        };
        if (!devResponse.ok || !devData.user) {
          throw new Error(
            devData.detail || "Tài khoản hoặc mật khẩu debug không chính xác.",
          );
        }
        createDevSession(devData.user);
        window.location.assign(POST_LOGIN_PATH);
        return;
      }

      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const data = (await response.json().catch(() => ({}))) as Partial<LoginResponse> & {
        detail?: string;
      };

      if (!response.ok || !data.access_token) {
        throw new Error(
          response.status === 401
            ? "Email hoặc mật khẩu không chính xác."
            : data.detail || "Không thể đăng nhập. Vui lòng thử lại.",
        );
      }

      localStorage.setItem("token", data.access_token);
      if (data.user) {
        localStorage.setItem("user", JSON.stringify(data.user));
      }
      window.location.assign(POST_LOGIN_PATH);
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : "Không thể đăng nhập. Vui lòng thử lại.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      {error && (
        <div className="login-error" role="alert">
          {error}
        </div>
      )}

      {DEV_AUTH_ENABLED && (
        <div className="login-dev-hint">
          <strong>Chế độ kiểm thử local</strong>
          <span>Dùng tài khoản debug trong web/.env.local</span>
        </div>
      )}

      <div className="login-field">
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          name="email"
          type="email"
          placeholder="ten@congty.com"
          autoComplete="email"
          required
        />
      </div>

      <div className="login-field">
        <span className="login-password-label">
          <label htmlFor="login-password">Mật khẩu</label>
          <Link href="/forgot-password">Quên mật khẩu?</Link>
        </span>
        <input
          id="login-password"
          name="password"
          type="password"
          placeholder="••••••••"
          autoComplete="current-password"
          minLength={8}
          required
        />
      </div>

      <button className="login-submit" type="submit" disabled={submitting}>
        {submitting ? "Đang đăng nhập..." : "Đăng nhập"}
      </button>
    </form>
  );
}
