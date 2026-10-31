
const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const DEFAULT_API_ERROR = "Something went wrong. Please try again.";

function getMessage(value) {
    if (typeof value === "string") {
        const message = value.trim();
        return message || null;
    }

    if (Array.isArray(value)) {
        const messages = value
            .map((item) => getMessage(item))
            .filter(Boolean);

        return messages.length > 0 ? messages.join(", ") : null;
    }

    if (value && typeof value === "object") {
        return getMessage(value.msg ?? value.message);
    }

    return null;
}

export function formatApiError(error, fallback = DEFAULT_API_ERROR) {
    const value = error instanceof Error ? error.message : error;
    return getMessage(value) || fallback;
}

export async function apiRequest(endpoint, options = {}) {
    const token = localStorage.getItem("openbench_token");

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options.headers,
        },
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
        const details = result.detail ?? result.message;
        const error = new Error(formatApiError(details));

        if (details !== undefined) {
            error.details = details;
        }

        throw error;
    }

    return result;
}
