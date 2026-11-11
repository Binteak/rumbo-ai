/** Nombres de los proveedores de modelo tal y como se muestran en la cabecera. */
const PROVIDER_LABELS: Record<string, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  groq: 'Groq',
  huggingface: 'Hugging Face',
  openrouter: 'OpenRouter',
  deepseek: 'DeepSeek',
};

/** "gemini" → "Gemini", "huggingface" → "Hugging Face"; uno desconocido, con la inicial en mayúscula. */
export function providerLabel(provider: string): string {
  if (!provider) return 'IA real';
  return PROVIDER_LABELS[provider] ?? provider[0].toUpperCase() + provider.slice(1);
}
