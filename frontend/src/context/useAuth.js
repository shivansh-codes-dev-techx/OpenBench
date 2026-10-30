import { useContext } from "react";
import { AuthContext } from "./AuthContextBase";

export function useAuth() {
    return useContext(AuthContext);
}
