const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8005/v1/pocket-money";

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

export const pocketMoneyApi = {
    // 1. Get the "Fine Catalog"
    getDeductionTypes: async (): Promise<DeductionType[]> => {
        const res = await fetch(`${API_BASE}/deductions`);
        if (!res.ok) throw new Error("Failed to load deductions catalog");
        return res.json();
    },

    // 2. Get Child Balance
    getBalance: async (childName: string) => {
        const res = await fetch(`${API_BASE}/balance/${childName}`);
        return res.json();
    },

    // 3. Submit the Fines
    submitDeductions: async (childId: number, items: BatchItem[], password: string) => {
        const res = await fetch(`${API_BASE}/deduct-batch/${childId}?password=${password}`, {
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

    addDeductionType: async (name: string, default_amount: number, password: string) => {
        const res = await fetch(`${API_BASE}/deductions?password=${password}`, { // Added password here
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name, default_amount}),
        });
        if (!res.ok) throw new Error("Failed to add new rule");
        return res.json();
    },

    getChildren: async () => {
        const res = await fetch(`${API_BASE}/children`);
        if (!res.ok) throw new Error("Failed to load children");
        return res.json();
    }
};
