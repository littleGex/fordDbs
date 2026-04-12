import {useState} from 'react';

interface Props {
    onRuleAdded: (name: string, amount: number) => Promise<void>;
}

export default function AddRuleForm({onRuleAdded}: Props) {
    const [name, setName] = useState('');
    const [amount, setAmount] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!name || !amount) return;

        try {
            await onRuleAdded(name, parseFloat(amount));
            setName('');   // Clear form on success
            setAmount('');
        } catch (err) {
            console.error("Form error:", err);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="mt-12 p-4 border-t border-gray-200 bg-white rounded-t-2xl">
            <h3 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-4">Add New House Rule</h3>
            <div className="flex gap-3 mt-2">
                <input
                    type="text"
                    placeholder="Rule name..."
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="flex-1 p-4 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none transition-all placeholder:text-gray-300"
                />
                <div className="relative w-48">
                    {/* 2. Moved Euro to the left side */}
                    <span
                        className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 font-bold pointer-events-none">
                        €
                    </span>
                    <input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        /* 3. Added pl-10 (padding-left) for the Euro, and made text larger/bolder */
                        className="w-full pl-10 pr-4 py-4 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none transition-all text-xl font-black text-gray-800"
                    />
                </div>
                <button
                    type="submit"
                    className="bg-red-500 text-white w-14 rounded-2xl font-bold shadow-lg shadow-red-200 hover:bg-red-600 active:scale-95 transition-all"
                >
                    +
                </button>
            </div>
        </form>
    );
}
