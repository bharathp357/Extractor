// API utility functions

const BASE = '';

export async function apiSend(prompt, provider, followup = false) {
  const res = await fetch(`${BASE}/api/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, provider, followup }),
  });
  return res.json();
}

export async function apiNewConversation(provider) {
  const res = await fetch(`${BASE}/api/new-conversation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider }),
  });
  return res.json();
}

export async function apiStatus() {
  const res = await fetch(`${BASE}/api/status`);
  return res.json();
}

export async function apiWarmup() {
  const res = await fetch(`${BASE}/api/warmup`);
  return res.json();
}

export async function apiReconnect(provider) {
  const res = await fetch(`${BASE}/api/reconnect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider }),
  });
  return res.json();
}

export async function apiHistory() {
  const res = await fetch(`${BASE}/api/history`);
  return res.json();
}

export async function apiReadHistory(filename) {
  const res = await fetch(`${BASE}/api/history/${filename}`);
  return res.json();
}

export async function apiDeleteHistory(filename) {
  const res = await fetch(`${BASE}/api/history/${filename}`, { method: 'DELETE' });
  return res.json();
}
