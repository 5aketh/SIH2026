const API_BASE_URL = "http://localhost:8000";

export async function fetchColorPoints() {
  const response = await fetch(`${API_BASE_URL}/api/points`);
  
  if (!response.ok) {
    throw new Error(`Backend error: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();

  if (!data || !Array.isArray(data) || data.length === 0) {
    throw new Error("Backend returned no points or invalid data.");
  }

  return data;
}