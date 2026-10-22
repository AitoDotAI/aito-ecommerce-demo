/** Money as the UCI data hold it, in pounds: "£2.95". Nothing is converted. */
export function fmtGbp(amount: number): string {
  return "£" + amount.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** "2011-11-06" as "6 Nov 2011". */
export function fmtDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}
