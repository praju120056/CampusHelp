export type Role = "faculty" | "hod" | "incharge" | "estate";

export type User = {
  id: number;
  name: string;
  email: string;
  role: Role;
  faculty_id: number | null;
};

const TOKEN_KEY = "educrew.token";
const USER_KEY = "educrew.user";

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_KEY) ?? null;
}

export function getUser(): User | null {
  const raw = storage()?.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function saveSession(token: string, user: User): void {
  storage()?.setItem(TOKEN_KEY, token);
  storage()?.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  storage()?.removeItem(TOKEN_KEY);
  storage()?.removeItem(USER_KEY);
}

export const HOME: Record<Role, string> = {
  faculty: "/log",
  hod: "/hod",
  incharge: "/tickets",
  estate: "/map",
};

export const ROLE_LABEL: Record<Role, string> = {
  faculty: "Faculty",
  hod: "HOD",
  incharge: "In-charge",
  estate: "Estate Officer",
};
