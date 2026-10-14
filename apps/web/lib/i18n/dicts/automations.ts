export const automations = {
  en: {
    chooseAutomation: "What would you like to automate?",
    handoffDestination: "Destination",
    recommendedTab: "Recommended", allTab: "All", multiDescription: "Select everything you want to automate. You can use several automations at the same time.", selectedCount: "{count} automations selected", configureSelected: "Configure selected", clear: "Clear", category: "Category", selectBusiness: "Select a business", chooseBusinessRecommendations: "Choose a business to see recommendations based on its industry and agents' objectives.", noRecommendations: "No recommendations yet. Explore All to choose automations.", comingSoon: "Coming soon", requiresIntegration: "Requires integration", forBusiness: "Recommended for your business", activationSummary: "Automations to activate", batchHelp: "Each block creates an independent automation for this business. Nothing is saved until you confirm this summary.", continue: "Continue", activateCount: "Save and activate {count} automations", handoffScope: "Transfer when the message contains this phrase. The conversation switches to human mode in Inbox; this action does not assign a team or person. Intent detection and attempt limits are not supported here.",


    "useTemplate": "Use template",
    "activate": "Activate automation",
    "custom": "Custom",
    "advancedCreate": "Create advanced automation",
    "advancedEdit": "Edit in advanced mode",
    "advancedWarning": "This rule includes options that require advanced mode. The simple form will not be available while they remain.",
    "scratchHelp": "For users who need full control over events, conditions and actions.",
    "recommended": "Recommended",
    "popular": "Popular",
    "pending": "Not available yet",
    "linkedChannel": "Linked conversation channel",
    "channelHelp": "Messages use the appointment’s linked conversation or the conversation that started the flow. Channel reply windows and human control still apply.",
    "keywordLabel": "Transfer when the message contains",
    "dataToSend": "Data to send (JSON)",
    "httpHelp": "Sends the fixed data entered here. Event data and message variables are not inserted automatically. GET does not send a body.",
    "noVariables": "This message is sent as written; variables are available only for appointment flows.",
    "appointmentHelp": "Requires a linked conversation. Reminders cover scheduled and confirmed appointments.",
    "defaultMessage": "Hello {{customer.name}}, your {{service.name}} appointment is on {{appointment_date}} at {{appointment_time}}.",
    "completedMessage": "Thank you for your visit, {{customer.name}}. Can we help you with anything else?",
    "businessUnavailable": "Business unavailable",
    "channel": "Channel",
    "unsupportedEdit": "This automation includes additional options. Use advanced mode to preserve them.",
    "discard": "Discard unsaved changes?",
    "categories": {
        "appointments": "Appointments",
        "sales": "Sales",
        "care": "Customer care",
        "integrations": "Integrations"
    },
    "catalog": {
        "confirmation": {
            "name": "Appointment confirmation",
            "description": "Send a confirmation when an appointment is created."
        },
        "reminder24": {
            "name": "Reminder 24 hours before",
            "description": "Remind customers one day before their appointment."
        },
        "reminder2": {
            "name": "Reminder 2 hours before",
            "description": "Remind customers two hours before their appointment."
        },
        "afterAppointment": {
            "name": "After-appointment follow-up",
            "description": "Send a message when an appointment is marked completed."
        },
        "followUp": {
            "name": "Automatic follow-up",
            "description": "Send a message after a conversation has been inactive. Any new message restarts the wait."
        },
        "recover": {
            "name": "Recover a lead",
            "description": "Contact again after a period without conversation activity."
        },
        "newLead": {
            "name": "New lead",
            "description": "Pending: the engine has no new-contact event. Business creation is a different event."
        },
        "welcome": {
            "name": "Welcome",
            "description": "Pending: a received message does not identify the start of a conversation."
        },
        "handoff": {
            "name": "Pass to a human",
            "description": "Transfer to human mode when a message contains a keyword."
        },
        "outOfHours": {
            "name": "Outside business hours",
            "description": "Pending: the engine does not evaluate business hours."
        },
        "webhook": {
            "name": "Send webhook",
            "description": "Send configured data to an external system when an event occurs."
        },
        "notify": {
            "name": "Notify an event",
            "description": "Notify an external system using an HTTP request."
        }
    }
,
    mine: "My automations", advanced: "Advanced mode", advancedHelp: "Create custom automations with events, conditions and actions.",
    reminder24: "Reminder 24 hours before", reminder2: "Reminder 2 hours before", reminderMessage: "Hello {{customer_name}}, a reminder of your {{service_name}} appointment on {{appointment_date}} at {{appointment_time}}.", variablesHelp: "Available: {{customer.name}}, {{customer.phone}}, {{customer.email}}, {{service.name}}, {{service.duration_minutes}}, {{appointment.id}}, {{appointment.starts_at}}, {{appointment.ends_at}}, {{appointment.status}}, {{client.name}}, {{appointment_date}}, {{appointment_time}}. Sending requires a linked conversation.", beforeAppointment: "Time before the appointment",
    title: "Automations", description: "Activate ready-made flows to reply, follow up and manage appointments without starting from scratch.",
    new: "New automation", edit: "Edit automation", name: "Name", client: "Business", allClients: "All businesses",
    empty: "Let everyday tasks take care of themselves", emptyDescription: "Create a follow-up, notify your team, or connect an API in a few simple steps.",
    when: "WHEN", whenHelp: "Choose the event that starts this automation.", if: "IF", ifHelp: "Optional. All conditions must match.",
    do: "DO", doHelp: "Actions run in this order. Waiting survives server restarts.",
    trigger: { message_received: "Message received", client_created: "Client created", conversation_inactive: "Conversation inactive", appointment_created: "Appointment created", appointment_rescheduled: "Appointment rescheduled", appointment_cancelled: "Appointment cancelled", appointment_completed: "Appointment completed", appointment_upcoming: "Before an appointment" },
    action: { send_message: "Send message", delay: "Wait", handoff_to_human: "Pass to a human", http_request: "Call webhook / API" },
    fields: { message: { text: "Message text" }, channel: "Channel", client: { name: "Business name", industry: "Industry" }, conversation: { mode: "Conversation mode" } },
    operators: { equals: "equals", not_equals: "does not equal", contains: "contains", not_contains: "does not contain", exists: "exists", not_exists: "does not exist" },
    status: { success: "Success", failed: "Failed", running: "Running", skipped: "Skipped" },
    errors: { appointment_changed: "The appointment was changed, cancelled or has already started.", evaluation_failed: "The rule could not be evaluated.", conversation_unavailable: "The conversation is closed or unavailable.", contact_blocked: "This contact is blocked.", url_blocked: "The URL is blocked or cannot be resolved.", http_failed: "The API returned an error or redirect.", human_control: "A human is handling this conversation.", channel_unsupported: "This channel does not support automated replies.", reply_window_closed: "The messaging reply window has closed.", action_unsupported: "Unsupported action.", delivery_uncertain: "Delivery was interrupted. Check the destination before sending again.", automation_changed: "The automation was changed, disabled, or its business is inactive.", new_activity: "There was more recent activity.", connection_failed: "The connection failed after retrying.", execution_failed: "The action could not be completed. Check its configuration and channel policy." },
    active: "Active", inactive: "Paused", enable: "Enable", disable: "Disable", enabled: "Automation enabled", disabled: "Automation disabled",
    save: "Save automation", saving: "Saving…", saved: "Automation saved", created: "Automation created", deleted: "Automation deleted",
    delete: "Delete", deleteConfirm: "Delete this automation and its history? Pending actions will be cancelled.",
    cancel: "Cancel", back: "Back to automations", editButton: "Edit", history: "History", lastRun: "Last run", never: "Not run yet",
    actionCount: "{count} actions", addAction: "Add action", addCondition: "Add condition", remove: "Remove", up: "Move up", down: "Move down",
    field: "Field", operator: "Operator", value: "Value", message: "Message", duration: "Duration", minutes: "Minutes", hours: "Hours", days: "Days",
    inactivityHelp: "Starts after a new message from either side. Any newer message cancels the older check. Historical and automation messages do not start checks.",
    sendHelp: "Uses the conversation's channel. Skipped while a human is in control; channel reply windows still apply.",
    clientHelp: "This event has no conversation. Use a delay or API request.", amount: "Amount", unit: "Unit",
    templates: "Templates", blank: "Start from scratch", followUp: "Automatic follow-up", handoff: "Pass to a human", webhook: "Send a webhook",
    followUpMessage: "Can I help you with any questions?", keyword: "human",
    method: "Method", url: "URL", headers: "Headers", query: "Query parameters", body: "JSON body", key: "Name", addPair: "Add field",
    headersHelp: "Saved header values are encrypted and hidden. Leave the mask unchanged to keep a saved value. Keep credentials in headers, not in the URL or body.",
    invalidJson: "Enter a valid JSON object for the API body.", error: "Could not complete the request. Check the fields, URL and your connection, then try again.",
    loadError: "Could not load automations.", retry: "Try again", historyEmpty: "No runs yet", historyHelp: "Runs appear when a matching event occurs after saving.",
    date: "Date", event: "Event", state: "Status", actionsExecuted: "Actions completed", elapsed: "Duration", errorLabel: "Details", seconds: "{count} s",
    refresh: "Refresh", more: "Load more", editHelp: "Saving changes cancels pending runs. An action already being sent may finish.",
    channelValues: "Channel values: whatsapp, whatsapp_cloud, widget, instagram, messenger. Modes: ai, human.",
  },
  es: {
    chooseAutomation: "¿Qué quieres automatizar?",
    handoffDestination: "Destino",
    recommendedTab: "Recomendadas", allTab: "Todas", multiDescription: "Selecciona todo lo que quieras automatizar. Puedes usar varias automatizaciones al mismo tiempo.", selectedCount: "{count} automatizaciones seleccionadas", configureSelected: "Configurar seleccionadas", clear: "Limpiar", category: "Categoría", selectBusiness: "Selecciona un negocio", chooseBusinessRecommendations: "Elige un negocio para ver recomendaciones según su industria y los objetivos de sus agentes.", noRecommendations: "Aún no hay recomendaciones. Explora Todas para elegir automatizaciones.", comingSoon: "Próximamente", requiresIntegration: "Requiere integración", forBusiness: "Recomendado para tu negocio", activationSummary: "Automatizaciones que se activarán", batchHelp: "Cada bloque crea una automatización independiente para este negocio. Nada se guarda hasta que confirmes este resumen.", continue: "Continuar", activateCount: "Guardar y activar {count} automatizaciones", handoffScope: "Transfiere cuando el mensaje contiene esta frase. La conversación pasa a modo humano en Inbox; esta acción no asigna equipo ni persona. Aquí no hay detección de intención ni límite de intentos.",


    "useTemplate": "Usar plantilla",
    "activate": "Activar automatización",
    "custom": "Personalizada",
    "advancedCreate": "Crear automatización avanzada",
    "advancedEdit": "Editar en modo avanzado",
    "advancedWarning": "Esta regla incluye opciones que requieren el modo avanzado. El formulario simple no estará disponible mientras se conserven.",
    "scratchHelp": "Para usuarios que necesitan control total sobre eventos, condiciones y acciones.",
    "recommended": "Recomendado",
    "popular": "Popular",
    "pending": "Pendiente de soporte",
    "linkedChannel": "Canal de la conversación vinculada",
    "channelHelp": "Los mensajes usan la conversación vinculada a la cita o la conversación que inició el flujo. Se respetan las ventanas del canal y el control humano.",
    "keywordLabel": "Transferir si el mensaje contiene",
    "dataToSend": "Datos a enviar (JSON)",
    "httpHelp": "Envía los datos fijos que escribas aquí. No se insertan datos del evento ni variables automáticamente. GET no envía cuerpo.",
    "noVariables": "Este mensaje se envía tal como se escribe; las variables solo están disponibles para citas.",
    "appointmentHelp": "Requiere una conversación vinculada. Los recordatorios incluyen citas programadas y confirmadas.",
    "defaultMessage": "Hola {{customer.name}}, tu cita de {{service.name}} es el {{appointment_date}} a las {{appointment_time}}.",
    "completedMessage": "Gracias por tu visita, {{customer.name}}. ¿Podemos ayudarte con algo más?",
    "businessUnavailable": "Negocio no disponible",
    "channel": "Canal",
    "unsupportedEdit": "Esta automatización incluye opciones adicionales. Usa el modo avanzado para conservarlas.",
    "discard": "¿Descartar los cambios sin guardar?",
    "categories": {
        "appointments": "Citas",
        "sales": "Ventas",
        "care": "Atención",
        "integrations": "Integraciones"
    },
    "catalog": {
        "confirmation": {
            "name": "Confirmación de cita",
            "description": "Envía una confirmación cuando se crea una cita."
        },
        "reminder24": {
            "name": "Recordatorio 24 horas antes",
            "description": "Envía un recordatorio un día antes de la cita."
        },
        "reminder2": {
            "name": "Recordatorio 2 horas antes",
            "description": "Envía un recordatorio dos horas antes de la cita."
        },
        "afterAppointment": {
            "name": "Seguimiento después de cita",
            "description": "Envía un mensaje al marcar una cita como completada."
        },
        "followUp": {
            "name": "Seguimiento automático",
            "description": "Envía un mensaje tras un periodo sin actividad. Cualquier mensaje nuevo reinicia la espera."
        },
        "recover": {
            "name": "Recuperar lead",
            "description": "Retoma el contacto después de un periodo sin actividad en la conversación."
        },
        "newLead": {
            "name": "Nuevo lead",
            "description": "Pendiente: el motor no tiene un evento de contacto nuevo. Crear un negocio es un evento distinto."
        },
        "welcome": {
            "name": "Bienvenida",
            "description": "Pendiente: recibir un mensaje no identifica el inicio de una conversación."
        },
        "handoff": {
            "name": "Pasar a humano",
            "description": "Pasa a modo humano cuando un mensaje contiene una palabra o frase."
        },
        "outOfHours": {
            "name": "Fuera de horario",
            "description": "Pendiente: el motor no evalúa horarios de atención."
        },
        "webhook": {
            "name": "Enviar webhook",
            "description": "Envía datos configurados a un sistema externo cuando ocurre un evento."
        },
        "notify": {
            "name": "Notificar evento",
            "description": "Notifica a un sistema externo mediante una solicitud HTTP."
        }
    }
,
    mine: "Mis automatizaciones", advanced: "Modo avanzado", advancedHelp: "Crea automatizaciones personalizadas con eventos, condiciones y acciones.",
    reminder24: "Recordatorio 24 horas antes", reminder2: "Recordatorio 2 horas antes", reminderMessage: "Hola {{customer_name}}, te recordamos tu cita de {{service_name}} para {{appointment_date}} a las {{appointment_time}}.", variablesHelp: "Variables: {{customer.name}}, {{customer.phone}}, {{customer.email}}, {{service.name}}, {{service.duration_minutes}}, {{appointment.id}}, {{appointment.starts_at}}, {{appointment.ends_at}}, {{appointment.status}}, {{client.name}}, {{appointment_date}}, {{appointment_time}}. El envío requiere una conversación vinculada.", beforeAppointment: "Tiempo antes de la cita",
    title: "Automatizaciones", description: "Activa flujos listos para responder, dar seguimiento y gestionar citas sin configurar todo desde cero.",
    new: "Nueva automatización", edit: "Editar automatización", name: "Nombre", client: "Negocio", allClients: "Todos los negocios",
    empty: "Deja que las tareas cotidianas se hagan solas", emptyDescription: "Crea un seguimiento, avisa a tu equipo o conecta una API en pocos pasos.",
    when: "CUANDO", whenHelp: "Elige el evento que inicia esta automatización.", if: "SI", ifHelp: "Opcional. Todas las condiciones deben cumplirse.",
    do: "HACER", doHelp: "Las acciones se ejecutan en este orden. Las esperas se conservan aunque el servidor se reinicie.",
    trigger: { message_received: "Mensaje recibido", client_created: "Cliente creado", conversation_inactive: "Conversación inactiva", appointment_created: "Cita creada", appointment_rescheduled: "Cita reprogramada", appointment_cancelled: "Cita cancelada", appointment_completed: "Cita completada", appointment_upcoming: "Antes de una cita" },
    action: { send_message: "Enviar mensaje", delay: "Esperar", handoff_to_human: "Pasar a humano", http_request: "Llamar webhook / API" },
    fields: { message: { text: "Texto del mensaje" }, channel: "Canal", client: { name: "Nombre del negocio", industry: "Industria" }, conversation: { mode: "Modo de conversación" } },
    operators: { equals: "es igual a", not_equals: "no es igual a", contains: "contiene", not_contains: "no contiene", exists: "existe", not_exists: "no existe" },
    status: { success: "Correcta", failed: "Fallida", running: "En curso", skipped: "Omitida" },
    errors: { appointment_changed: "La cita cambió, se canceló o ya comenzó.", evaluation_failed: "No se pudo evaluar la regla.", conversation_unavailable: "La conversación está cerrada o no está disponible.", contact_blocked: "Este contacto está bloqueado.", url_blocked: "La URL está bloqueada o no se puede resolver.", http_failed: "La API devolvió un error o una redirección.", human_control: "Un operador está atendiendo esta conversación.", channel_unsupported: "Este canal no admite respuestas automáticas.", reply_window_closed: "La ventana de respuesta del canal ha cerrado.", action_unsupported: "Acción no compatible.", delivery_uncertain: "El envío se interrumpió. Revisa el destino antes de volver a enviar.", automation_changed: "La automatización cambió, se desactivó o su negocio está inactivo.", new_activity: "Hubo actividad más reciente.", connection_failed: "La conexión falló después de reintentar.", execution_failed: "No se pudo completar la acción. Revisa su configuración y las políticas del canal." },
    active: "Activa", inactive: "Pausada", enable: "Activar", disable: "Desactivar", enabled: "Automatización activada", disabled: "Automatización desactivada",
    save: "Guardar automatización", saving: "Guardando…", saved: "Automatización guardada", created: "Automatización creada", deleted: "Automatización eliminada",
    delete: "Eliminar", deleteConfirm: "¿Eliminar esta automatización y su historial? Se cancelarán las acciones pendientes.",
    cancel: "Cancelar", back: "Volver a automatizaciones", editButton: "Editar", history: "Historial", lastRun: "Última ejecución", never: "Sin ejecuciones",
    actionCount: "{count} acciones", addAction: "Agregar acción", addCondition: "Agregar condición", remove: "Quitar", up: "Subir", down: "Bajar",
    field: "Campo", operator: "Operador", value: "Valor", message: "Mensaje", duration: "Duración", minutes: "Minutos", hours: "Horas", days: "Días",
    inactivityHelp: "Se programa tras un mensaje nuevo de cualquiera de las partes. Un mensaje posterior cancela la comprobación anterior. Los mensajes históricos y de automatizaciones no inician comprobaciones.",
    sendHelp: "Usa el canal de la conversación. Se omite si un humano tiene el control y respeta las ventanas de respuesta del canal.",
    clientHelp: "Este evento no tiene una conversación. Usa una espera o una llamada API.", amount: "Cantidad", unit: "Unidad",
    templates: "Plantillas", blank: "Crear desde cero", followUp: "Seguimiento automático", handoff: "Pasar a humano", webhook: "Enviar webhook",
    followUpMessage: "¿Te puedo ayudar con alguna duda?", keyword: "humano",
    method: "Método", url: "URL", headers: "Encabezados", query: "Parámetros de consulta", body: "Cuerpo JSON", key: "Nombre", addPair: "Agregar campo",
    headersHelp: "Los valores guardados se cifran y se ocultan. Conserva la máscara para mantener un valor guardado. Guarda las credenciales en encabezados, no en la URL ni en el cuerpo.",
    invalidJson: "Introduce un objeto JSON válido para el cuerpo de la API.", error: "No se pudo completar la solicitud. Revisa los campos, la URL y tu conexión e inténtalo de nuevo.",
    loadError: "No se pudieron cargar las automatizaciones.", retry: "Reintentar", historyEmpty: "Aún no hay ejecuciones", historyHelp: "Las ejecuciones aparecerán cuando ocurra un evento coincidente después de guardar.",
    date: "Fecha", event: "Evento", state: "Estado", actionsExecuted: "Acciones completadas", elapsed: "Duración", errorLabel: "Detalles", seconds: "{count} s",
    refresh: "Actualizar", more: "Cargar más", editHelp: "Guardar cambios cancela las ejecuciones pendientes. Una acción que ya se está enviando puede finalizar.",
    channelValues: "Valores de canal: whatsapp, whatsapp_cloud, widget, instagram, messenger. Modos: ai, human.",
  },
};
