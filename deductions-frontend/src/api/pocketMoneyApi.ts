const API_BASE = import.meta.env.VITE_API_BASE || "http://192.168.2.51:8005/v1/pocket-money";
// Logins are shared with Fordstagram, which lives next to pocket-money
const AUTH_BASE = API_BASE.replace(/\/pocket-money\/?$/, "/family-photos");

const TOKEN_KEY = "token";
const PARENT_ROLES = ["parent", "admin"];

export interface DeductionType {
    id: number;
    name: string;
    default_amount: number;
}

export interface BatchItem {
    name: string;
    count: number;
    total: number;
}

export interface FamilyUser {
    id: number;
    display_name: string;
}

// Thrown when the token is missing, expired or not a parent's
export class AuthError extends Error {}

export const session = {
    isLoggedIn: () => !!localStorage.getItem(TOKEN_KEY),
    logout: () => localStorage.removeItem(TOKEN_KEY),
};

// fetch() with the login token attached
const authFetch = async (path: string, init: RequestInit = {}) => {
    const res = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: {
            ...init.headers,
            Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}`,
        },
    });
    if (res.status === 401 || res.status === 403) {
        session.logout();
        throw new AuthError("Please log in again");
    }
    return res;
};

export const pocketMoneyApi = {
    // The parents, who are the only ones this app is for
    getFamily: async (): Promise<FamilyUser[]> => {
        const res = await fetch(`${AUTH_BASE}/login-options?audience=parents`);
        if (!res.ok) throw new Error("Failed to load the family list");
        return res.json();
    },

    login: async (userId: number, password: string) => {
        const res = await fetch(`${AUTH_BASE}/login`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({user_id: userId, password}),
        });
        if (res.status === 401) throw new Error("Wrong password");
        // 403 and 429 carry the reason, e.g. an account still waiting for
        // approval, or too many wrong passwords
        if (res.status === 403 || res.status === 429) throw new Error((await res.json()).detail);
        if (!res.ok) throw new Error("Login failed");
        const data = await res.json();
        if (!PARENT_ROLES.includes(data.user.role)) {
            throw new Error("Parents only");
        }
        localStorage.setItem(TOKEN_KEY, data.access_token);
    },

    // 1. Get the "Fine Catalog"
    getDeductionTypes: async (): Promise<DeductionType[]> => {
        const res = await authFetch("/deductions");
        if (!res.ok) throw new Error("Failed to load deductions catalog");
        return res.json();
    },

    // 2. Get Child Balance
    getBalance: async (childName: string) => {
        const res = await authFetch(`/balance/${childName}`);
        return res.json();
    },

    // 3. Submit the Fines
    submitDeductions: async (childId: number, items: BatchItem[]) => {
        const res = await authFetch(`/deduct-batch/${childId}`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(items),
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Transaction failed");
        }
        return res.json();
    },

    addDeductionType: async (name: string, default_amount: number) => {
        const res = await authFetch("/deductions", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name, default_amount}),
        });
        if (!res.ok) throw new Error("Failed to add new rule");
        return res.json();
    },

    getChildren: async () => {
        const res = await authFetch("/children");
        if (!res.ok) throw new Error("Failed to load children");
        return res.json();
    }
};
