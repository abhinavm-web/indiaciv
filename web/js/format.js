export function compact(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return (n / 1e12).toFixed(a >= 1e13 ? 1 : 2) + "T";
  if (a >= 1e9) return (n / 1e9).toFixed(a >= 1e11 ? 0 : 1) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e8 ? 0 : 1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
  return String(Math.round(n));
}

// Indian rupees in Indian notation: 1 lakh = 100,000; 1 crore = 10,000,000; "lakh crore" = 10^12.
export function inr(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return "₹" + (n / 1e12).toFixed(a >= 1e13 ? 1 : 2).replace(/\.?0+$/, "") + " lakh cr";
  if (a >= 1e7) return "₹" + (n / 1e7).toLocaleString("en-IN", { maximumFractionDigits: a >= 1e9 ? 0 : 1 }) + " cr";
  if (a >= 1e5) return "₹" + (n / 1e5).toFixed(1).replace(/\.0$/, "") + " lakh";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}
export const money = inr;
export const dollars = (n) => (n == null ? "–" : "₹" + Math.round(n).toLocaleString("en-IN"));
export const int = (n) => (n == null ? "–" : Math.round(n).toLocaleString("en-US"));
export const pct = (x, d = 1) => (x == null ? "–" : (x * 100).toFixed(d) + "%");

export function yieldValue(y, v) {
  return y.unit === "inr" ? money(v) : compact(v);
}

export function popShort(n) {
  if (n >= 1e7) return Math.round(n / 1e6) + "M";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  return Math.round(n / 1e3) + "K";
}

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
