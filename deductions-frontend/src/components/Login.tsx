import { useEffect, useState } from 'react';
import { pocketMoneyApi, type FamilyUser } from '../api/pocketMoneyApi';

interface Props {
    onLogin: () => void;
}

export default function Login({ onLogin }: Props) {
    const [family, setFamily] = useState<FamilyUser[]>([]);
    const [userId, setUserId] = useState<number | null>(null);
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        pocketMoneyApi.getFamily()
            .then(setFamily)
            .catch((err: Error) => setError(err.message));
    }, []);

    const submit = async () => {
        if (userId === null || !password || busy) return;
        setBusy(true);
        setError('');
        try {
            await pocketMoneyApi.login(userId, password);
            onLogin();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Login failed");
        } finally {
            setPassword('');
            setBusy(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center p-4">
            <div className="bg-white w-full max-w-sm rounded-3xl p-8 shadow-2xl">
                <h1 className="text-4xl font-black text-gray-950 tracking-tight mb-2">Deductions</h1>
                <p className="text-gray-500 mb-6 font-medium">Parents only. Who are you?</p>

                <div className="grid grid-cols-2 gap-3 mb-6">
                    {family.map(member => (
                        <button
                            key={member.id}
                            onClick={() => setUserId(member.id)}
                            className={`py-3 rounded-2xl font-bold transition-all ${userId === member.id ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700'}`}
                        >
                            {member.display_name}
                        </button>
                    ))}
                </div>

                {userId !== null && (
                    <>
                        <input
                            autoFocus
                            type="password"
                            placeholder="Password"
                            autoComplete="current-password"
                            className="w-full p-4 bg-gray-100 rounded-2xl border-none outline-none focus:ring-2 focus:ring-red-500 mb-6 font-bold"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && submit()}
                        />
                        <button
                            disabled={busy || !password}
                            onClick={submit}
                            className="w-full py-4 bg-gray-900 text-white rounded-2xl font-bold shadow-lg disabled:bg-gray-200 active:scale-95 transition-all"
                        >
                            Log in
                        </button>
                    </>
                )}

                {error && <p className="text-red-600 font-bold mt-4">{error}</p>}
            </div>
        </div>
    );
}
