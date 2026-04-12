import { useState } from 'react';

interface Props {
    isOpen: boolean;
    title: string;
    description?: string;
    onConfirm: (password: string) => void;
    onCancel: () => void;
}

export default function PasswordModal({ isOpen, title, description, onConfirm, onCancel }: Props) {
    const [password, setPassword] = useState('');

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />

            {/* Modal Content */}
            <div className="relative bg-white w-full max-w-sm rounded-3xl p-8 shadow-2xl animate-scale-in">
                <h3 className="text-2xl font-black text-gray-900 mb-2">{title}</h3>
                {description && <p className="text-gray-500 mb-6 font-medium">{description}</p>}

                <input
                    autoFocus
                    type="password"
                    placeholder="Enter Admin Password"
                    className="w-full p-4 bg-gray-100 rounded-2xl border-none outline-none focus:ring-2 focus:ring-red-500 mb-6 font-bold"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && onConfirm(password)}
                />

                <div className="flex gap-3">
                    <button onClick={onCancel} className="flex-1 py-4 font-bold text-gray-400 hover:text-gray-600">
                        Cancel
                    </button>
                    <button
                        onClick={() => onConfirm(password)}
                        className="flex-1 py-4 bg-gray-900 text-white rounded-2xl font-bold shadow-lg active:scale-95 transition-all"
                    >
                        Confirm
                    </button>
                </div>
            </div>
        </div>
    );
}
