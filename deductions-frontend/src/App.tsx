import {useState, useEffect} from 'react';
import {pocketMoneyApi, type DeductionType} from './api/pocketMoneyApi';
import DeductionItem from './components/DeductionItem';
import AddRuleForm from './components/AddRuleForm';
import Toast from './components/Toast'; // Fixed casing to match component
import PasswordModal from "./components/PasswordModal";

function App() {
    const [catalog, setCatalog] = useState<DeductionType[]>([]);
    const [counts, setCounts] = useState<{ [key: string]: number }>({});
    const [loading, setLoading] = useState(true);
    const [childId, setChildId] = useState(1);
    const [children, setChildren] = useState<{ id: number, name: string }[]>([]);

    // UI Feedback State
    const [toast, setToast] = useState<{msg: string, type: 'success' | 'error'} | null>(null);
    const [modal, setModal] = useState<{isOpen: boolean, type: 'FINES' | 'RULE', data?: any}>({
        isOpen: false,
        type: 'FINES'
    });

    useEffect(() => {
        const init = async () => {
            try {
                const [catalogData, childrenData] = await Promise.all([
                    pocketMoneyApi.getDeductionTypes(),
                    pocketMoneyApi.getChildren()
                ]);
                setCatalog(catalogData);
                setChildren(childrenData);
            } catch (err) {
                console.error("Failed to load initial data:", err);
            } finally {
                setLoading(false);
            }
        };
        init();
    }, []);

    const handleUpdateCount = (name: string, delta: number) => {
        setCounts(prev => {
            const currentCount = prev[name] || 0;
            const newCount = Math.max(0, Math.round(currentCount + delta));
            return {...prev, [name]: newCount};
        });
    };

    const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
        setToast({ msg, type });
    };

    const handleSubmit = () => setModal({ isOpen: true, type: 'FINES' });

    const handleAddRule = async (name: string, amount: number) => {
        setModal({ isOpen: true, type: 'RULE', data: { name, amount } });
    };

    const totalFine = catalog.reduce((sum, item) => sum + ((counts[item.name] || 0) * item.default_amount), 0);

    const onPasswordConfirm = async (password: string) => {
        setModal(prev => ({ ...prev, isOpen: false }));
        try {
            if (modal.type === 'FINES') {
                const batch = Object.entries(counts)
                    .filter(([_, count]) => count > 0)
                    .map(([name, count]) => {
                        const item = catalog.find(i => i.name === name);
                        return { name, count, total: count * (item?.default_amount || 0) };
                    });

                await pocketMoneyApi.submitDeductions(childId, batch, password);
                setCounts({});
                showToast("Deductions applied successfully!");
            } else if (modal.type === 'RULE') {
                await pocketMoneyApi.addDeductionType(modal.data.name, modal.data.amount, password);
                const updated = await pocketMoneyApi.getDeductionTypes();
                setCatalog(updated);
                showToast("New house rule added!");
            }
        } catch (err: any) {
            showToast(err.message || "Action failed", "error");
        }
    };

    if (loading) return <div className="p-8 text-center font-bold text-gray-500">Connecting to Ford Home Apps...</div>;

    return (
        <div className="min-h-screen bg-[#F8F9FA]">
            {/* Overlay UI */}
            {toast && <Toast message={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
            <PasswordModal
                isOpen={modal.isOpen}
                title={modal.type === 'FINES' ? "Confirm Fines" : "Add New Rule"}
                description={modal.type === 'FINES' ? `Apply ${totalFine.toFixed(2)}€ to ${children.find(c => c.id === childId)?.name}?` : undefined}
                onConfirm={onPasswordConfirm}
                onCancel={() => setModal(prev => ({ ...prev, isOpen: false }))}
            />

            <div className="max-w-x1 mx-auto pb-40">
                <header className="p-8 pb-4 flex justify-between items-center">
                    <h1 className="text-4xl font-black text-gray-950 tracking-tight">Deductions</h1>
                    <select
                        value={childId}
                        onChange={(e) => setChildId(parseInt(e.target.value))}
                        className="appearance-none bg-white shadow-sm rounded-xl px-4 py-2 font-bold text-gray-700 ring-1 ring-black/5 outline-none"
                    >
                        {children.map(child => <option key={child.id} value={child.id}>{child.name}</option>)}
                    </select>
                </header>

                <main className="px-6 space-y-4">
                    {catalog.map(item => (
                        <DeductionItem
                            key={item.id}
                            item={item}
                            count={counts[item.name] || 0}
                            onUpdate={handleUpdateCount}
                        />
                    ))}

                    <div className="pt-4 opacity-50">
                        <div className="h-px bg-gray-200 w-full"/>
                    </div>

                    <AddRuleForm onRuleAdded={handleAddRule}/>
                </main>

                <footer className="fixed bottom-0 left-0 right-0 p-6 bg-white/80 backdrop-blur-md border-t border-gray-100 flex items-center justify-between z-50">
                    <div className="flex flex-col">
                        <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest leading-none mb-1">Total Fine: </span>
                        <span className="text-3xl font-black text-red-600 leading-none">{totalFine.toFixed(2)}€</span>
                    </div>
                    <button
                        disabled={totalFine === 0}
                        onClick={handleSubmit}
                        className="bg-gray-900 text-white px-10 py-4 rounded-2xl font-bold shadow-xl disabled:bg-gray-200 transition-all active:scale-95"
                    >
                        Confirm
                    </button>
                </footer>
            </div>
        </div>
    );
}

export default App;
