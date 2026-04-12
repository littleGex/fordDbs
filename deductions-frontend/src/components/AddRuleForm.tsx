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
            <div className="flex gap-3 mt-2 items-center"> {/* added items-center */}
                <input
                    type="text"
                    placeholder="Rule name..."
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="flex-1 h-14 px-4 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none transition-all placeholder:text-gray-300"
                />

                <div className="relative w-40 shrink-0 h-14">
    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 font-bold pointer-events-none">
        €
    </span>
                    <input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        /* Using h-full with py-0 and leading-none often resolves browser clipping for arrows */
                        className="w-full h-full pl-10 pr-2 py-0 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none transition-all text-base font-black text-gray-900 leading-none"
                    />
                </div>

                <button
                    type="submit"
                    /* Changed w-14 to px-6 to make it a rounded square/rectangle instead of a sliver */
                    className="bg-red-500 text-white h-14 px-6 rounded-2xl font-bold shadow-lg shadow-red-200 hover:bg-red-600 active:scale-95 transition-all flex items-center justify-center shrink-0"
                >
                    <span className="text-2xl">+</span> {/* Explicit size for the plus */}
                </button>
            </div>
        </form>
    );
}
