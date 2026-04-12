import { useEffect } from 'react';

interface Props {
    message: string;
    type: 'success' | 'error';
    onClose: () => void;
}

export default function Toast({ message, type, onClose }: Props) {
    useEffect(() => {
        const timer = setTimeout(onClose, 3000); // Auto-close after 3s
        return () => clearTimeout(timer);
    }, [onClose]);

    const bgColor = type === 'success' ? 'bg-green-600' : 'bg-red-600';

    return (
        <div className={`fixed top-6 left-1/2 -translate-x-1/2 z-[100] px-6 py-3 rounded-full text-white font-bold shadow-2xl ${bgColor} animate-bounce-in`}>
            {message}
        </div>
    );
}
