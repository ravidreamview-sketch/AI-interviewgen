const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

function getAuthHeader(): Record<string, string> {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token") || sessionStorage.getItem("token");
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...getAuthHeader(),
    ...(options.headers as Record<string, string>),
  };

  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = API_BASE ? `${API_BASE}${cleanEndpoint}` : cleanEndpoint;

  try {
    const response = await fetch(url, {
      credentials: "include",
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed with status ${response.status}`);
    }

    return response.json();
  } catch (err: any) {
    if (err.name === "TypeError" && (err.message === "Failed to fetch" || err.message?.includes("fetch"))) {
      throw new Error(`Unable to reach the backend API at ${url}. Please ensure the server is active.`);
    }
    throw err;
  }
}
