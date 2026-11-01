
import { apiRequest } from "../api/client";

export const authService = {
    async login(credentials) {
        return apiRequest("/auth/login", {
            method: "POST",
            body: JSON.stringify(credentials),
        });
    },

    async register(userData) {
        return apiRequest("/auth/register", {
            method: "POST",
            body: JSON.stringify(userData),
        });
    },

    async getCurrentUser() {
        return apiRequest("/auth/me");
    },
};
