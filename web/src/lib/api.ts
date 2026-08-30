export async function requestJson<T = any>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  if (data === null) throw new Error("The server returned an invalid response.");
  return data as T;
}
