import { type DeductionType } from '../api/pocketMoneyApi';

// 1. Define what "Props" (variables) this component needs to work
interface Props {
  item: DeductionType;
  count: number;
  onUpdate: (name: string, delta: number) => void;
}

// 2. Build the Component
export default function DeductionItem({ item, count, onUpdate }: Props) {
  return (
    <div className="flex items-center justify-between p-4 bg-white rounded-lg shadow-sm border border-gray-200">

      {/* Left side: Name and Price */}
      <div>
        <p className="font-semibold text-gray-800">{item.name}</p>
        <p className="text-sm text-gray-500">${item.default_amount.toFixed(2)} each</p>
      </div>

      {/* Right side: Buttons */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => onUpdate(item.name, -1)}
          className="w-8 h-8 flex items-center justify-center rounded-full bg-gray-100 hover:bg-gray-200 text-xl"
        >
          -
        </button>

        <span className="w-4 text-center font-bold">
          {count}
        </span>

        <button
          onClick={() => onUpdate(item.name, 1)}
          className="w-8 h-8 flex items-center justify-center rounded-full bg-red-100 text-red-600 hover:bg-red-200 text-xl"
        >
          +
        </button>
      </div>

    </div>
  );
}
