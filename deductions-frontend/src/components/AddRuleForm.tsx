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
            <div className="flex gap-3 mt-2 items-end">
                {/* Rule Name - Flexes to fill space */}
                <div className="flex-1 flex flex-col gap-1">
                    <label className="text-[10px] font-black text-gray-400 uppercase ml-2">Rule Name</label>
                    <input
                        type="text"
                        placeholder="e.g. Unmade Bed"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full h-14 px-4 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none"
                    />
                </div>

                {/* Amount - Fixed to 90px width */}
                <div className="w-[90px] shrink-0 flex flex-col gap-1">
                    <label className="text-[10px] font-black text-gray-400 uppercase ml-2">Amount</label>
                    <div className="relative h-14">
                        <input
                            type="text"
                            value={amount}
                            onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))}
                            className="w-full h-full pl-3 pr-2 bg-white rounded-2xl border-none shadow-sm ring-1 ring-black/5 focus:ring-red-500 outline-none text-center font-black text-gray-900"
                        />
                    </div>
                </div>

                {/* Side-by-Side Adjustment Arrows */}
                <div className="flex flex-col gap-1 h-14 shrink-0">
                    <button
                        type="button"
                        onClick={() => setAmount(prev => (parseFloat(prev || '0') + 0.5).toFixed(2))}
                        className="flex-1 bg-gray-100 hover:bg-gray-200 px-3 rounded-t-lg text-xs font-bold"
                    >▲
                    </button>
                    <button
                        type="button"
                        onClick={() => setAmount(prev => Math.max(0, parseFloat(prev || '0') - 0.5).toFixed(2))}
                        className="flex-1 bg-gray-100 hover:bg-gray-200 px-3 rounded-b-lg text-xs font-bold"
                    >▼
                    </button>
                </div>

                {/* Submit Button */}
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
