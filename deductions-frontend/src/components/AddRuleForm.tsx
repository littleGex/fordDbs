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
            <div className="flex gap-4 mt-2 items-end"> {/* Changed gap to 4 and items-end */}
                <div className="flex-1 flex flex-col gap-1">
                    <label className="text-[10px] font-bold text-gray-400 uppercase ml-2">Rule Name</label>
                    <input
                        type="text"
                        placeholder="e.g. Unmade Bed"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full h-14 px-4 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none transition-all"
                    />
                </div>

                <div className="w-44 shrink-0 flex flex-col gap-1">
                    <label className="text-[10px] font-bold text-gray-400 uppercase ml-2">Amount</label>
                    <div className="relative h-14">
    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 font-bold pointer-events-none">
        €
    </span>
                        <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={amount}
                            onChange={(e) => setAmount(e.target.value)}
                            /* Removed py-1 and added py-0.
                               Changed text-base to text-lg but used font-bold instead of font-black
                               to keep the text "thinner" vertically.
                            */
                            className="w-full h-full pl-10 pr-2 py-0 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none text-lg font-bold text-gray-900 leading-none"
                        />
                    </div>
                </div>

                <button
                    type="submit"
                    className="bg-red-500 text-white h-14 w-14 rounded-2xl font-bold shadow-lg shadow-red-200 hover:bg-red-600 active:scale-95 transition-all flex items-center justify-center shrink-0"
                >
                    <span className="text-2xl">+</span>
                </button>
            </div>
        </form>
    );
}
