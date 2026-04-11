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
        setCounts(prev => ({...prev, [name]: Math.max(0, (prev[name] || 0) + delta)}));
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
        <div className="max-w-md mx-auto p-4 bg-gray-50 min-h-screen font-sans">
            <header className="mb-6 flex justify-between items-center">
                <h1 className="text-2xl font-bold text-red-600">Deductions</h1>

                {/* 2. Updated Select to use the actual children state */}
                <select
                    value={childId}
                    onChange={(e) => setChildId(parseInt(e.target.value))}
                    className="p-2 border rounded bg-white text-gray-800 shadow-sm"
                >
                    {children.map(child => (
                        <option key={child.id} value={child.id}>
                            {child.name}
                        </option>
                    ))}
                </select>
            </header>

            <div className="space-y-3">
                {catalog.map(item => (
                    <DeductionItem key={item.id} item={item} count={counts[item.name] || 0}
                                   onUpdate={handleUpdateCount}/>
                ))}
            </div>

            <footer className="mt-8 p-6 bg-white rounded-xl shadow-lg border-t-4 border-red-500 sticky bottom-4">
                <div className="flex justify-between items-center mb-4">
                    <span className="text-2xl font-black text-red-600">${totalFine.toFixed(2)}</span>
                    <button
                        disabled={totalFine === 0}
                        onClick={handleSubmit}
                        className="bg-red-600 text-white px-6 py-2 rounded-lg font-bold disabled:bg-gray-300"
                    >
                        Deduct
                    </button>
                </div>
            </footer>

            {/* 3. Fixed prop name to match AddRuleForm.tsx */}
            <AddRuleForm onRuleAdded={handleAddRule}/>
        </div>
    );
}

export default App;
