import { NextResponse } from "next/server";

export async function POST(request: Request) {
  if (
    process.env.NODE_ENV !== "development" ||
    process.env.NEXT_PUBLIC_DASHBOARD_MOCK_MODE !== "true"
  ) {
    return NextResponse.json({ detail: "Không tìm thấy." }, { status: 404 });
  }

  const expectedEmail = process.env.DEV_LOGIN_EMAIL;
  const expectedPassword = process.env.DEV_LOGIN_PASSWORD;
  if (!expectedEmail || !expectedPassword) {
    return NextResponse.json(
      { detail: "Chưa cấu hình tài khoản debug trong .env.local." },
      { status: 503 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as {
    email?: string;
    password?: string;
  };
  if (body.email !== expectedEmail || body.password !== expectedPassword) {
    return NextResponse.json(
      { detail: "Tài khoản hoặc mật khẩu debug không chính xác." },
      { status: 401 },
    );
  }

  return NextResponse.json({
    user: {
      id: "local-development-user",
      email: expectedEmail,
      name: "Auralis Local",
      role: "admin",
      assigned_site_ids: [],
      must_change_password: false,
    },
  });
}
