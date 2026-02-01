const getChildren = async () => {
  try {
    // Note: Use your Pi's IP or 'localhost' if testing locally
    const response = await fetch('http://localhost:8005/v1/pocket-money/children');
    const data = await response.json();
    children.value = data;
  } catch (error) {
    console.error("Failed to fetch children:", error);
  }
};
