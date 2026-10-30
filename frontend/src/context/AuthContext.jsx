import { useEffect, useState } from "react";
import { AuthContext } from "./AuthContextBase";
import { authService } from "../services/authService";

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);

    const [loading, setLoading] = useState(
        () => Boolean(localStorage.getItem("openbench_token"))
    );

    useEffect(() => {
        const token = localStorage.getItem("openbench_token");

        if (!token) return;

        authService
            .getCurrentUser()
            .then((response) => {
                setUser(response.data?.user ?? response.data);
            })
            .catch(() => {
                localStorage.removeItem("openbench_token");
                setUser(null);
            })
            .finally(() => {
                setLoading(false);
            });
    }, []);

    async function login(credentials) {
        const response = await authService.login(credentials);
        const authData = response.data;

        localStorage.setItem("openbench_token", authData.access_token);
        setUser(authData.user);

        return authData.user;
    }

    async function register(userData) {
        const response = await authService.register(userData);
        const authData = response.data;

        localStorage.setItem("openbench_token", authData.access_token);
        setUser(authData.user);

        return authData.user;
    }

    function logout() {
        localStorage.removeItem("openbench_token");
        setUser(null);
    }

    return (
        <AuthContext.Provider
            value={{ user, loading, login, register, logout }}
        >
            {children}
        </AuthContext.Provider>
    );
}
