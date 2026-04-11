import {useState, useEffect} from 'react';
import {pocketMoneyApi, type DeductionType, type BatchItem} from './api/pocketMoneyApi';
import DeductionItem from './components/DeductionItem';
import AddRuleForm from './components/AddRuleForm';

function App() {
    const [catalog, setCatalog] = useState<DeductionType[]>([]);
    const [counts, setCounts] = useState<{ [key: string]: number }>({});
    const [loading, setLoading] = useState(true);
    const [childId, setChildId] = useState(1);
    const [children, setChildren] = useState<{ id: number, name: string }[]>([]);

    // 1. Updated Fetch data logic to include children
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

    // Actions
    const handleUpdateCount = (name: string, delta: number) => {
        setCounts(prev => {
            const currentCount = prev[name] || 0;
            const newCount = currentCount + delta;

            // Gap Fix: Only allow 0 or higher (no negative integers)
            return {
                ...prev,
                [name]: Math.max(0, Math.floor(newCount))
            };
        });
    };

    const handleAddRule = async (name: string, amount: number) => {
        const password = prompt("Enter Admin Password to add a new rule:");
        if (!password) return;

        try {
            await pocketMoneyApi.addDeductionType(name, amount, password); // Pass the password
            const updatedCatalog = await pocketMoneyApi.getDeductionTypes();
            setCatalog(updatedCatalog);
        } catch (err: any) {
            alert("Could not save rule: " + err.message);
        }
    };

    const handleSubmit = async () => {
        const password = prompt("Enter Admin Password:");
        if (!password) return;

        const items: BatchItem[] = catalog
            .filter(item => (counts[item.name] || 0) > 0)
            .map(item => ({
                name: item.name,
                count: counts[item.name],
                total: counts[item.name] * item.default_amount
            }));

        try {
            await pocketMoneyApi.submitDeductions(childId, items, password);
            alert("Success!");
            setCounts({});
        } catch (err: any) {
            alert(err.message);
        }
    };

    const totalFine = catalog.reduce((sum, item) => sum + ((counts[item.name] || 0) * item.default_amount), 0);

    if (loading) return <div className="p-8 text-center">Connecting to Ford Home Apps...</div>;

    return (
        <div className="max-w-md mx-auto min-h-screen bg-[#F8F9FA] font-sans pb-24">
            {/* Clean Header */}
            <header className="p-6 pt-10">
                <div className="flex justify-between items-end mb-8">
                    <div>
                        <h1 className="text-3xl font-black text-gray-900 tracking-tight">Deductions</h1>
                        <p className="text-gray-400 text-sm font-medium">Ford Home Apps</p>
                    </div>
                    <select
                        value={childId}
                        onChange={(e) => setChildId(parseInt(e.target.value))}
                        className="bg-white border-none shadow-sm rounded-xl px-4 py-2 text-gray-700 font-bold outline-none ring-1 ring-black/5"
                    >
                        {children.map(child => (
                            <option key={child.id} value={child.id}>{child.name}</option>
                        ))}
                    </select>
                </div>

                {/* Catalog List */}
                <div className="space-y-1">
                    {catalog.map(item => (
                        <DeductionItem
                            key={item.id}
                            item={item}
                            count={counts[item.name] || 0}
                            onUpdate={handleUpdateCount}
                        />
                    ))}
                </div>
            </header>

            {/* Floating Footer Summary */}
            <footer
                className="fixed bottom-0 left-0 right-0 p-6 bg-white/90 backdrop-blur-md border-t border-gray-100 flex items-center justify-between z-50">
                <div className="flex flex-col">
                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">To Deduct</span>
                    <span className="text-3xl font-black text-red-600 leading-none">
      {totalFine.toFixed(2)}€
    </span>
                </div>

                <button
                    disabled={totalFine === 0}
                    onClick={handleSubmit}
                    className="bg-gray-900 text-white px-10 py-4 rounded-2xl font-bold shadow-xl shadow-gray-200 disabled:bg-gray-200 disabled:shadow-none transition-all active:scale-95"
                >
                    Confirm
                </button>
            </footer>

            {/* Form at bottom of scroll */}
            <div className="px-6 pb-12">
                <AddRuleForm onRuleAdded={handleAddRule}/>
            </div>
        </div>
    );
}

export default App;
