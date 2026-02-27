export const PROVIDERS = {
  google:  { name: 'Google AI Mode', short: 'AI Mode',  color: '#4285f4', dimColor: 'rgba(66,133,244,0.12)',  initials: 'G' },
  gemini:  { name: 'Gemini Pro',     short: 'Gemini',   color: '#a855f7', dimColor: 'rgba(168,85,247,0.12)', initials: 'G' },
  chatgpt: { name: 'ChatGPT',        short: 'ChatGPT',  color: '#10a37f', dimColor: 'rgba(16,163,127,0.12)', initials: 'C' },
};

export const PROVIDER_KEYS = ['google', 'gemini', 'chatgpt'];

export const SUGGESTIONS = [
  { icon: 'Sparkles', text: 'Explain quantum computing in simple terms' },
  { icon: 'Code',     text: 'Write a Python REST API with Flask' },
  { icon: 'ArrowLeftRight', text: 'Compare React, Vue, and Angular frameworks' },
  { icon: 'Bug',      text: 'Help me debug a performance issue' },
];
