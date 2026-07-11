/** Design-system primitives — the ONE component directory (charter §3). */
import type { ReactNode } from "react";

export function Button(props: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
}) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-slate-300",
    ghost: "border border-slate-300 text-slate-700 hover:bg-slate-50",
    danger: "bg-rose-600 text-white hover:bg-rose-500",
  }[props.variant ?? "primary"];
  return (
    <button
      type={props.type ?? "button"}
      onClick={props.onClick}
      disabled={props.disabled}
      className={`rounded-md px-3 py-1.5 text-sm font-medium ${styles}`}
    >
      {props.children}
    </button>
  );
}

export function Field(props: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-600">{props.label}</span>
      {props.children}
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none";

export function Input(props: {
  name?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
}) {
  return (
    <input
      {...props}
      onChange={(e) => props.onChange?.(e.target.value)}
      className={inputCls}
    />
  );
}

export function Select(props: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
      className={inputCls}
    >
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Card(props: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {(props.title || props.actions) && (
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">{props.title}</h2>
          <div className="flex gap-2">{props.actions}</div>
        </header>
      )}
      {props.children}
    </section>
  );
}

export function Table(props: { headers: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
            {props.headers.map((h) => (
              <th key={h} className="px-2 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{props.children}</tbody>
      </table>
    </div>
  );
}

export function Badge(props: { children: ReactNode; tone?: "ok" | "warn" | "info" | "muted" }) {
  const tones = {
    ok: "bg-emerald-100 text-emerald-800",
    warn: "bg-amber-100 text-amber-800",
    info: "bg-indigo-100 text-indigo-800",
    muted: "bg-slate-100 text-slate-600",
  }[props.tone ?? "muted"];
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tones}`}>
      {props.children}
    </span>
  );
}

export function ErrorText(props: { error: unknown }) {
  if (!props.error) return null;
  const message = props.error instanceof Error ? props.error.message : String(props.error);
  return (
    <p role="alert" className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
      {message}
    </p>
  );
}

export function Empty(props: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-500">{props.children}</p>;
}
