
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "")
    .trim()
    .replace(/\/+$/, "");

function getErrorMessage(value) {
    if (Array.isArray(value)) {
        return value
            .map((item) => {
                if (typeof item === "string") return item;
                return item?.msg || item?.message || "Validation error";
            })
            .join(", ");
    }

    if (typeof value === "string" && value.trim()) {
        return value;
    }

    if (value && typeof value === "object") {
        return value.message || value.msg || "The server rejected the request.";
    }

    return "";
}

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
    if (!API_BASE_URL) {
        throw new Error(
            "VITE_API_BASE_URL is not configured. Set it in the frontend environment."
        );
    }

    const token = localStorage.getItem("openbench_token");
    const isFormData = options.body instanceof FormData;

    const headers = new Headers(options.headers || {});

    // For FormData, the browser must set Content-Type
    // automatically, including the multipart boundary.
    if (isFormData) {
        headers.delete("Content-Type");
    } else if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    // Attach authentication token when available.
    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers,
    });

    const responseText = await response.text();
    let result = {};

    if (responseText) {
        try {
            result = JSON.parse(responseText);
        } catch {
            if (response.ok) {
                throw new Error("The server returned an invalid response.");
            }
        }
    }

    if (!response.ok) {
        const details = result.detail ?? result.message;

        const message =
            getErrorMessage(details) ||
            `Request failed (${response.status}).`;

        const error = new Error(message);
        error.status = response.status;

        if (details !== undefined) {
            error.details = details;
        }

        throw error;
    }

    return result;
}
