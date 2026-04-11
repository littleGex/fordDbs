import { useState } from 'react';

interface Props {
  onRuleAdded: (name: string, amount: number) => Promise<void>;
}

export default function AddRuleForm({ onRuleAdded }: Props) {
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
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="e.g. Messy Room"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="flex-1 p-3 border rounded-lg bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none"
        />
        <input
          type="number"
          step="0.10"
          placeholder="0.50"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="w-24 p-3 border rounded-lg bg-gray-50 outline-none"
        />
        <button
          type="submit"
          className="bg-blue-600 text-white px-5 py-3 rounded-lg font-bold hover:bg-blue-700 active:scale-95 transition-all"
        >
          +
        </button>
      </div>
    </form>
  );
}
