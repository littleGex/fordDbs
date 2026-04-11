import { type DeductionType } from '../api/pocketMoneyApi';

interface Props {
  item: DeductionType;
  count: number;
  onUpdate: (name: string, delta: number) => void;
}

export default function DeductionItem({ item, count, onUpdate }: Props) {
  return (
    <div className="flex items-center justify-between p-5 bg-white rounded-2xl shadow-sm mb-3 border border-gray-50">
      <div>
        <p className="font-bold text-gray-800 text-lg leading-tight">{item.name}</p>
        <p className="text-sm text-gray-400 font-semibold">{item.default_amount.toFixed(2)}€ each</p>
      </div>

      <div className="flex items-center gap-4 bg-gray-100 rounded-xl p-1">
        <button
          onClick={() => onUpdate(item.name, -1)} // Still sends -1, but App.tsx will block < 0
          className="w-10 h-10 flex items-center justify-center rounded-lg bg-white shadow-sm text-gray-500 hover:bg-gray-200 transition-all active:scale-90"
        >
          -
        </button>

        <span className="w-6 text-center font-black text-gray-700">
          {count}
        </span>

        <button
          onClick={() => onUpdate(item.name, 1)}
          className="w-10 h-10 flex items-center justify-center rounded-lg bg-red-500 text-white shadow-md hover:bg-red-600 transition-all active:scale-90"
        >
          +
        </button>
      </div>
    </div>
  );
}
