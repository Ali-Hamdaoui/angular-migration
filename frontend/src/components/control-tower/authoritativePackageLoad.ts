export type AuthoritativePackageLoad<T> =
  | { status: "loading" }
  | { status: "ready"; value: T }
  | { status: "unavailable"; retry: () => void }
  | { status: "error"; retry: () => void };
