const en = {
  defaultName: "Groq main",
  description: "Cloud · Fast AI models running on Groq infrastructure.",
  empty: "No models were found for this account.",
  unauthorized: "Could not connect to Groq. Check the API key.",
  rate_limit: "Groq temporarily reached its request limit. Try again in a few seconds.",
  timeout: "Groq timed out. Try again.", unavailable: "Could not connect to Groq.",
  invalid_response: "Groq returned an invalid response.", model_missing: "The selected model is unavailable.",
  not_configured: "Configure Groq in Settings first.",
  tools_unconfirmed: "Function calling could not be confirmed for this model. Choose another model or disable tools.",
  tool_limit: "The model exceeded the tool call limit.", apiKey: "Groq API key", capabilityHint: "Checking tool compatibility sends a small Groq request and consumes provider usage.",
};
const es: typeof en = {
  defaultName: "Groq principal",
  description: "Cloud · Modelos de IA rápidos ejecutados en la infraestructura de Groq.",
  empty: "No se encontraron modelos disponibles en esta cuenta.",
  unauthorized: "No se pudo conectar con Groq. Comprueba la API key.",
  rate_limit: "Groq alcanzó temporalmente el límite de solicitudes. Intenta nuevamente en unos segundos.",
  timeout: "Groq agotó el tiempo de espera. Intenta nuevamente.", unavailable: "No se pudo conectar con Groq.",
  invalid_response: "Groq devolvió una respuesta inválida.", model_missing: "El modelo seleccionado no está disponible.",
  not_configured: "Configura Groq en Configuración primero.",
  tools_unconfirmed: "No se pudo confirmar compatibilidad con herramientas. Elige otro modelo o desactiva las herramientas.",
  tool_limit: "El modelo superó el límite de llamadas a herramientas.", apiKey: "API key de Groq", capabilityHint: "Comprobar herramientas envía una pequeña solicitud a Groq y consume uso del proveedor.",
};
export const groq = { en, es };
