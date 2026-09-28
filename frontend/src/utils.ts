export function formatDate(value: string | null): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds - minutes * 60;
  return `${minutes}:${remaining.toFixed(2).padStart(5, "0")}`;
}

export function readableType(value: string): string {
  if (!value) return "";
  if (value.includes("_")) {
    return value
      .split("_")
      .map((w) => {
        if (w.toLowerCase() === "uturn") return "U-Turn";
        return w.charAt(0).toUpperCase() + w.slice(1);
      })
      .join(" ");
  }
  return value.replace(/([a-z])([A-Z])/g, "$1 $2");
}
